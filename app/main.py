import os
import queue
import shutil
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver

from .config import SCHEMA_VERSION, load_settings
from .monitoring import configure_logging, health_status, metrics
from .retention import cleanup
from .storage import fetch_records, list_snapshot_files, read_last_processed, write_schema_version
from .tasks import TaskRunner, _parse_snapshot_time
from .usage import summarize_usage

settings = load_settings()
configure_logging(settings.logs_dir / "app.log", settings.log_level)
write_schema_version(settings.data_dir, SCHEMA_VERSION)
WEB_DIR = Path(os.getenv("WEB_DIR", "/web"))
if not WEB_DIR.exists():
    fallback = Path(__file__).resolve().parent.parent / "web"
    if fallback.exists():
        WEB_DIR = fallback


app = FastAPI()
runner = TaskRunner(settings, metrics)
ASK_MAX_LOOKBACK_HOURS = 168
ASK_MAX_ITEMS = 200
DESCRIPTIONS_MAX_LIMIT = 2000
RANGE_MAX_HOURS = 168
RANGE_MAX_ITEMS = 400
STORY_MAX_HOURS = 168
STORY_MAX_ITEMS = 48
HIGHLIGHT_MAX_HOURS = 168
HIGHLIGHT_MAX_ITEMS = 1000


def _is_api_key_valid(request: Request) -> bool:
    if not settings.api_key:
        return True
    supplied = request.headers.get("X-API-Key") or request.query_params.get("api_key")
    return supplied == settings.api_key


@app.middleware("http")
async def _api_key_guard(request: Request, call_next):
    if settings.api_key and (request.url.path.startswith("/api/") or request.url.path.startswith("/data/")):
        if not _is_api_key_valid(request):
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
    return await call_next(request)

snapshot_queue: queue.Queue[Path] = queue.Queue()
enqueued_paths: set[Path] = set()
enqueued_lock = threading.Lock()


class CompareRequest(BaseModel):
    snapshot_a: str
    snapshot_b: str


class AskRequest(BaseModel):
    query: str
    lookback_hours: Optional[int] = None
    max_items: Optional[int] = None


class RangeSummaryRequest(BaseModel):
    start: str
    end: str
    max_items: Optional[int] = None


class NoCacheStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store"
        return response


def _load_last_processed() -> dict:
    data = read_last_processed(settings.run_dir / "last_processed.json")
    if isinstance(data, dict):
        return data
    return {}


def _load_last_processed_path() -> None:
    last_processed = _load_last_processed()
    if last_processed.get("path"):
        try:
            runner.last_processed_path = Path(last_processed["path"])
            runner.last_seen_path = runner.last_processed_path
        except OSError:
            runner.last_processed_path = None
            runner.last_seen_path = None
    if last_processed.get("timestamp"):
        metrics.last_snapshot_time = last_processed["timestamp"]


def _enqueue_snapshot(path: Path) -> None:
    if not _is_snapshot(path):
        return
    with enqueued_lock:
        if path in enqueued_paths:
            return
        enqueued_paths.add(path)
    snapshot_queue.put(path)


class SnapshotHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        _enqueue_snapshot(Path(event.src_path))

    def on_moved(self, event):
        if event.is_directory:
            return
        _enqueue_snapshot(Path(event.dest_path))


def _is_snapshot(path: Path) -> bool:
    return path.suffix.lower() in {".jpg", ".jpeg", ".png"} and not path.name.endswith(".tmp")


def _worker() -> None:
    while True:
        path = snapshot_queue.get()
        try:
            runner.process_snapshot(path)
        except Exception as exc:  # noqa: BLE001
            logger.error("Processing failed for {path}: {error}", path=str(path), error=str(exc))
        finally:
            with enqueued_lock:
                enqueued_paths.discard(path)
            snapshot_queue.task_done()


def _scan_new_snapshots() -> None:
    last_processed = _load_last_processed()
    last_ts = _parse_iso(last_processed.get("timestamp"))
    for path in list_snapshot_files(settings.snapshots_dir):
        ts = _parse_snapshot_time(path, settings)
        if ts is None:
            continue
        if last_ts is None or ts > last_ts:
            _enqueue_snapshot(path)


def _parse_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_range_value(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid datetime format") from exc
    if parsed.tzinfo is None:
        if hasattr(settings.tz, "localize"):
            parsed = settings.tz.localize(parsed)
        else:
            parsed = parsed.replace(tzinfo=settings.tz)
    return parsed.astimezone(timezone.utc)


def _start_watchdog() -> None:
    handler = SnapshotHandler()
    observer = PollingObserver() if settings.camera_source == "windows-host" else Observer()
    observer.schedule(handler, str(settings.snapshots_dir), recursive=True)
    observer.daemon = True
    observer.start()


def _resolve_snapshot_path(path_value: str) -> Path:
    if not path_value:
        raise HTTPException(status_code=400, detail="snapshot path required")
    trimmed = path_value
    if trimmed.startswith("/data/"):
        trimmed = trimmed[len("/data/"):]
    trimmed = trimmed.lstrip("/")
    data_root = settings.data_dir.resolve()
    snapshots_root = settings.snapshots_dir.resolve()
    candidate = (data_root / trimmed).resolve()
    if snapshots_root not in candidate.parents:
        candidate = (snapshots_root / trimmed).resolve()
    if snapshots_root not in candidate.parents:
        raise HTTPException(status_code=400, detail="snapshot path must be under snapshots directory")
    if candidate.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
        raise HTTPException(status_code=400, detail="invalid snapshot file type")
    if not candidate.exists():
        raise HTTPException(status_code=404, detail="snapshot not found")
    return candidate


scheduler = BackgroundScheduler(timezone=settings.tz)


def _schedule_jobs() -> None:
    if settings.camera_source in {"http", "rtsp"}:
        scheduler.add_job(
            _capture_job,
            IntervalTrigger(minutes=settings.capture_interval_min),
            id="capture",
            replace_existing=True,
        )
    if settings.camera_source == "windows-host":
        scheduler.add_job(
            _scan_new_snapshots,
            IntervalTrigger(minutes=1),
            id="scan",
            replace_existing=True,
        )
    scheduler.add_job(
        runner.compare_recent,
        IntervalTrigger(minutes=10),
        id="compare_10m",
        replace_existing=True,
    )
    scheduler.add_job(
        runner.compare_hourly,
        CronTrigger(minute=0),
        id="compare_hourly",
        replace_existing=True,
    )
    scheduler.add_job(
        runner.daily_report,
        CronTrigger(hour=0, minute=5),
        id="daily_report",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: cleanup(settings),
        CronTrigger(hour=1, minute=0),
        id="retention_cleanup",
        replace_existing=True,
    )


def _capture_job() -> None:
    if settings.camera_source == "http":
        path = runner.capture_snapshot_http()
    else:
        path = runner.capture_snapshot_rtsp()
    if path:
        _enqueue_snapshot(path)


@app.on_event("startup")
def _on_startup() -> None:
    _load_last_processed_path()
    threading.Thread(target=_worker, daemon=True).start()
    if settings.camera_source == "windows-host":
        _start_watchdog()
    _scan_new_snapshots()
    _schedule_jobs()
    scheduler.start()


@app.get("/")
def root():
    return FileResponse(str(WEB_DIR / "index.html"), headers={"Cache-Control": "no-store"})


@app.get("/api/config")
def api_config():
    return {
        "ui_refresh_interval_sec": settings.ui_refresh_interval_sec,
        "timezone": settings.timezone,
        "ask_enabled": settings.ask_enabled,
        "ask_lookback_hours": settings.ask_lookback_hours,
        "ask_max_items": settings.ask_max_items,
        "preview_cooldown_sec": settings.preview_cooldown_sec,
    }


@app.get("/api/health")
def api_health():
    usage = shutil.disk_usage(settings.data_dir)
    disk_free_mb = usage.free / (1024 * 1024)
    queue_depth = snapshot_queue.qsize()
    status = health_status(
        metrics.last_snapshot_time,
        disk_free_mb,
        queue_depth,
        settings.capture_interval_min,
    )
    return JSONResponse(
        {
            "status": status,
            "last_snapshot_time": metrics.last_snapshot_time,
            "last_api_success": {
                "groq": metrics.last_groq_success,
                "gemini": metrics.last_gemini_success,
            },
            "last_api_failure": {
                "groq": metrics.last_groq_failure,
                "gemini": metrics.last_gemini_failure,
            },
            "disk_free_mb": round(disk_free_mb, 2),
            "queue_depth": queue_depth,
        },
        status_code=200 if status in {"healthy", "degraded"} else 503,
    )


@app.get("/api/metrics")
def api_metrics():
    usage = shutil.disk_usage(settings.data_dir)
    disk_used_mb = usage.used / (1024 * 1024)
    disk_free_mb = usage.free / (1024 * 1024)
    return JSONResponse(metrics.to_metrics_json(disk_used_mb, disk_free_mb))


@app.get("/api/usage/summary")
def api_usage_summary(days: int = 7):
    window_days = max(1, min(days, 90))
    return summarize_usage(settings, window_days)


@app.get("/api/snapshots/latest")
def api_latest_snapshot():
    snapshots = list_snapshot_files(settings.snapshots_dir)
    if not snapshots:
        return {"snapshot": None, "timestamp": None}
    latest = snapshots[-1]
    ts = _parse_snapshot_time(latest, settings)
    timestamp = ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if ts else None
    try:
        rel_path = latest.relative_to(settings.data_dir).as_posix()
    except ValueError:
        rel_path = latest.as_posix()
    return {
        "snapshot": f"/data/{rel_path}",
        "timestamp": timestamp,
    }


@app.get("/api/preview")
def api_preview():
    preview_path = runner.capture_preview()
    if preview_path and preview_path.exists():
        return FileResponse(preview_path, headers={"Cache-Control": "no-store"})

    snapshots = list_snapshot_files(settings.snapshots_dir)
    if not snapshots:
        raise HTTPException(status_code=404, detail="no preview available")
    return FileResponse(snapshots[-1], headers={"Cache-Control": "no-store"})


@app.get("/api/descriptions")
def api_descriptions(limit: Optional[int] = None, offset: int = 0):
    if limit is None:
        return fetch_records(settings.data_dir, "descriptions")
    safe_limit = max(1, min(limit, DESCRIPTIONS_MAX_LIMIT))
    safe_offset = max(0, offset)
    items = fetch_records(
        settings.data_dir,
        "descriptions",
        limit=safe_limit,
        offset=safe_offset,
        newest_first=True,
    )
    return list(reversed(items))


@app.get("/api/compare/10m")
def api_compare_10m():
    return fetch_records(settings.data_dir, "compare_10m")


@app.get("/api/compare/hourly")
def api_compare_hourly():
    return fetch_records(settings.data_dir, "compare_hourly")


@app.post("/api/compare/custom")
def api_compare_custom(request: CompareRequest):
    if request.snapshot_a == request.snapshot_b:
        raise HTTPException(status_code=400, detail="snapshots must differ")
    path_a = _resolve_snapshot_path(request.snapshot_a)
    path_b = _resolve_snapshot_path(request.snapshot_b)
    record = runner.compare_custom(path_a, path_b)
    if record.get("error"):
        raise HTTPException(status_code=500, detail="compare failed")
    return record


@app.post("/api/ask")
def api_ask(request: AskRequest):
    if not settings.ask_enabled:
        raise HTTPException(status_code=403, detail="ask disabled")
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="query required")
    lookback_hours = (
        request.lookback_hours if request.lookback_hours is not None else settings.ask_lookback_hours
    )
    max_items = request.max_items if request.max_items is not None else settings.ask_max_items
    lookback_hours = max(1, min(lookback_hours, ASK_MAX_LOOKBACK_HOURS))
    max_items = max(1, min(max_items, ASK_MAX_ITEMS))
    result = runner.ask_feed(query, lookback_hours, max_items)
    if result.get("error"):
        raise HTTPException(status_code=502, detail="ask failed")
    return result


@app.post("/api/summary/range")
def api_summary_range(request: RangeSummaryRequest):
    if not settings.ask_enabled:
        raise HTTPException(status_code=403, detail="ask disabled")
    start = _parse_range_value(request.start)
    end = _parse_range_value(request.end)
    if end <= start:
        raise HTTPException(status_code=400, detail="end must be after start")
    if end - start > timedelta(hours=RANGE_MAX_HOURS):
        raise HTTPException(
            status_code=400,
            detail=f"range must be <= {RANGE_MAX_HOURS} hours",
        )
    max_items = request.max_items if request.max_items is not None else settings.ask_max_items
    max_items = max(1, min(max_items, RANGE_MAX_ITEMS))
    result = runner.summarize_range(start, end, max_items)
    if result.get("error"):
        raise HTTPException(status_code=502, detail="range summary failed")
    return result


@app.get("/api/story/daily")
def api_story_daily(hours: int = 24, max_items: int = STORY_MAX_ITEMS):
    if not settings.ask_enabled:
        raise HTTPException(status_code=403, detail="ask disabled")
    lookback_hours = max(1, min(hours, STORY_MAX_HOURS))
    safe_max_items = max(1, min(max_items, STORY_MAX_ITEMS))
    result = runner.story_arc(lookback_hours, safe_max_items)
    if result.get("error"):
        raise HTTPException(status_code=502, detail="story arc failed")
    return result


@app.get("/api/highlights/daily")
def api_highlights_daily(hours: int = 24, max_items: int = HIGHLIGHT_MAX_ITEMS):
    if not settings.ask_enabled:
        raise HTTPException(status_code=403, detail="ask disabled")
    lookback_hours = max(1, min(hours, HIGHLIGHT_MAX_HOURS))
    safe_max_items = max(1, min(max_items, HIGHLIGHT_MAX_ITEMS))
    return runner.highlight_reel(lookback_hours, safe_max_items)


@app.get("/api/reports/daily")
def api_reports_daily():
    return fetch_records(settings.data_dir, "daily_reports")


app.mount("/web", NoCacheStaticFiles(directory=str(WEB_DIR), html=True), name="web")
app.mount("/data/snapshots", StaticFiles(directory=str(settings.snapshots_dir)), name="snapshots")

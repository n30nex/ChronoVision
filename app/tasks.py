import base64
import json
import re
import subprocess
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx
from loguru import logger

from . import prompts, storage
from .image_validator import diff_percent, is_dark_frame, validate_image
from .rate_limiter import RateLimiter
from .usage import record_usage

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
RTSP_CAPTURE_TIMEOUT_SEC = 30


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def local_timestamp(settings) -> datetime:
    return datetime.now(settings.tz)


def build_snapshot_path(settings, dt_local: datetime) -> Path:
    rel_dir = Path(dt_local.strftime("%Y/%m/%d"))
    filename = dt_local.strftime("%H%M%S") + ".jpg"
    return settings.snapshots_dir / rel_dir / filename


def ensure_stable_file(path: Path, attempts: int = 3, delay: float = 0.5) -> bool:
    last_size = -1
    for _ in range(attempts):
        try:
            size = path.stat().st_size
        except OSError:
            return False
        if size == last_size and size > 0:
            return True
        last_size = size
        time.sleep(delay)
    return False


def encode_image(path: Path) -> tuple[str, str]:
    mime = "image/jpeg"
    suffix = path.suffix.lower()
    if suffix == ".png":
        mime = "image/png"
    with open(path, "rb") as handle:
        data = base64.b64encode(handle.read()).decode("ascii")
    return mime, data


def safe_truncate(text: str, limit: int = 200) -> str:
    cleaned = " ".join(text.strip().split())
    if len(cleaned) <= limit:
        return cleaned
    sentences = [s.strip() for s in cleaned.replace("!", ".").replace("?", ".").split(".")]
    result = []
    for sentence in sentences:
        if not sentence:
            continue
        candidate = ". ".join(result + [sentence])
        if len(candidate) + 1 > limit:
            break
        result.append(sentence)
    if result:
        return ". ".join(result).rstrip(".") + "."
    truncated = cleaned[:limit]
    if " " in truncated:
        truncated = truncated.rsplit(" ", 1)[0]
    return truncated.rstrip() + "."


def _call_with_retry(limiter: RateLimiter, provider: str, max_attempts: int, func):
    last_exc = None
    last_latency = 0.0
    for attempt in range(1, max_attempts + 1):
        limiter.acquire()
        start = time.time()
        try:
            result = func()
            last_latency = (time.time() - start) * 1000
            limiter.record_success()
            return result, last_latency, None
        except Exception as exc:  # noqa: BLE001
            last_latency = (time.time() - start) * 1000
            limiter.record_failure()
            last_exc = exc
            logger.warning(
                "{provider} attempt {attempt} failed: {error}",
                provider=provider,
                attempt=attempt,
                error=str(exc),
            )
            if attempt < max_attempts:
                limiter.backoff(attempt)
    return None, last_latency, last_exc


def _extract_openai_usage(payload: dict) -> dict[str, int]:
    usage = payload.get("usage", {}) if isinstance(payload, dict) else {}
    return {
        "input_tokens": int(usage.get("prompt_tokens", 0)),
        "output_tokens": int(usage.get("completion_tokens", 0)),
        "total_tokens": int(usage.get("total_tokens", 0)),
    }


def _extract_gemini_usage(payload: dict) -> dict[str, int]:
    usage = payload.get("usageMetadata", {}) if isinstance(payload, dict) else {}
    prompt_tokens = int(usage.get("promptTokenCount", 0))
    output_tokens = int(usage.get("candidatesTokenCount", 0))
    total_tokens = int(usage.get("totalTokenCount", prompt_tokens + output_tokens))
    return {
        "input_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def _extract_json_object(text: str) -> dict | None:
    if not text:
        return None
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _normalize_tags(data: dict | None) -> dict[str, list[str]]:
    tags = {"people": [], "vehicles": [], "objects": []}
    if not isinstance(data, dict):
        return tags
    for key in tags:
        values = data.get(key, [])
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list):
            continue
        cleaned = []
        for value in values:
            if not isinstance(value, str):
                continue
            item = value.strip().lower()
            if item and item not in cleaned:
                cleaned.append(item)
        tags[key] = cleaned
    return tags


def _format_tags_summary(tags: dict[str, list[tuple[str, int]]]) -> str:
    parts = []
    for key, items in tags.items():
        if not items:
            continue
        formatted = ", ".join([f"{label}({count})" for label, count in items])
        parts.append(f"{key}: {formatted}")
    return "; ".join(parts) if parts else "none"


def _format_tags_compact(tags: dict | None) -> str:
    if not isinstance(tags, dict):
        return "none"
    parts = []
    for key in ("people", "vehicles", "objects"):
        values = tags.get(key, [])
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list):
            continue
        cleaned = [v.strip() for v in values if isinstance(v, str) and v.strip()]
        if cleaned:
            parts.append(f"{key}: {', '.join(cleaned[:4])}")
    return "; ".join(parts) if parts else "none"


def _build_ask_context(
    items: list[dict],
    settings,
    max_items: int,
) -> tuple[str, int, str, str]:
    sorted_items = sorted(
        items,
        key=lambda item: _parse_iso(item.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc),
    )
    sliced = sorted_items[-max_items:] if max_items > 0 else sorted_items
    lines = []
    timestamps = []
    for item in sliced:
        ts = _parse_iso(item.get("timestamp"))
        if ts:
            timestamps.append(ts)
            local_ts = ts.astimezone(settings.tz).strftime("%Y-%m-%d %H:%M")
        else:
            local_ts = item.get("timestamp") or "unknown time"
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        text = safe_truncate(text, 160)
        tags_line = _format_tags_compact(item.get("tags"))
        line = f"- {local_ts}: {text}"
        if tags_line != "none":
            line += f" (tags: {tags_line})"
        lines.append(line)

    if timestamps:
        start = min(timestamps).astimezone(settings.tz)
        end = max(timestamps).astimezone(settings.tz)
        if start.date() == end.date():
            window_label = f"{start:%Y-%m-%d} {start:%H:%M} - {end:%H:%M}"
        else:
            window_label = f"{start:%Y-%m-%d %H:%M} - {end:%Y-%m-%d %H:%M}"
    else:
        window_label = "recent snapshots"

    tags_summary = _format_tags_summary(_aggregate_tags(sliced))
    return "\n".join(lines), len(lines), window_label, tags_summary


class TaskRunner:
    def __init__(self, settings, metrics):
        self.settings = settings
        self.metrics = metrics
        self.groq_limiter = RateLimiter(
            settings.groq_rate_limit_rpm,
            settings.api_retry_max_attempts,
            settings.api_retry_base_delay,
            settings.api_circuit_breaker_threshold,
        )
        self.gemini_limiter = RateLimiter(
            settings.gemini_rate_limit_rpm,
            settings.api_retry_max_attempts,
            settings.api_retry_base_delay,
            settings.api_circuit_breaker_threshold,
        )
        self.last_processed_path: Optional[Path] = None
        self.last_seen_path: Optional[Path] = None
        self.last_preview_path: Optional[Path] = None
        self.last_preview_time = 0.0

    def _capture_http(self, target: Path) -> Optional[Path]:
        if not self.settings.camera_http_url:
            logger.error("CAMERA_HTTP_URL is not set")
            return None
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_path = target.with_suffix(".tmp")
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(self.settings.camera_http_url)
                resp.raise_for_status()
                temp_path.write_bytes(resp.content)
            temp_path.replace(target)
            return target
        except Exception as exc:  # noqa: BLE001
            logger.error("HTTP capture failed: {error}", error=str(exc))
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            return None

    def _capture_rtsp(self, target: Path) -> Optional[Path]:
        if not self.settings.camera_rtsp_url:
            logger.error("CAMERA_RTSP_URL is not set")
            return None
        ffmpeg = self.settings.ffmpeg_path or "ffmpeg"
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_path = target.with_suffix(".tmp")
        cmd = [
            ffmpeg,
            "-rtsp_transport",
            "tcp",
            "-i",
            self.settings.camera_rtsp_url,
            "-vframes",
            "1",
            "-q:v",
            "2",
            str(temp_path),
        ]
        try:
            subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=RTSP_CAPTURE_TIMEOUT_SEC,
            )
            temp_path.replace(target)
            return target
        except subprocess.TimeoutExpired:
            logger.error("RTSP capture timed out after {seconds}s", seconds=RTSP_CAPTURE_TIMEOUT_SEC)
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.error("RTSP capture failed: {error}", error=str(exc))
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            return None

    def capture_snapshot_http(self) -> Optional[Path]:
        dt_local = local_timestamp(self.settings)
        target = build_snapshot_path(self.settings, dt_local)
        return self._capture_http(target)

    def capture_snapshot_rtsp(self) -> Optional[Path]:
        dt_local = local_timestamp(self.settings)
        target = build_snapshot_path(self.settings, dt_local)
        return self._capture_rtsp(target)

    def capture_preview(self) -> Optional[Path]:
        preview_path = self.settings.run_dir / "preview.jpg"
        now = time.time()
        if (
            self.last_preview_path
            and self.last_preview_path.exists()
            and self.settings.preview_cooldown_sec > 0
            and (now - self.last_preview_time) < self.settings.preview_cooldown_sec
        ):
            return self.last_preview_path

        captured = None
        if self.settings.camera_source == "http":
            captured = self._capture_http(preview_path)
        elif self.settings.camera_source == "rtsp":
            captured = self._capture_rtsp(preview_path)
        if captured:
            self.last_preview_path = captured
            self.last_preview_time = now
        return captured

    def process_snapshot(self, path: Path) -> None:
        lock_path = self.settings.run_dir / "processing.lock"
        with storage.file_lock(lock_path):
            if not path.exists():
                return
            if not ensure_stable_file(path):
                logger.warning("Snapshot file not stable yet: {path}", path=str(path))
                return
            valid, reason = validate_image(path, self.settings)
            if not valid:
                logger.warning("Invalid image {path}: {reason}", path=str(path), reason=reason)
                return
            if self.settings.dark_frame_check and is_dark_frame(path):
                logger.warning("Dark frame detected, skipping: {path}", path=str(path))
                return

            previous_path = self.last_seen_path
            self.last_seen_path = path

            if (
                self.settings.motion_detection_enabled
                and previous_path
                and previous_path.exists()
            ):
                change = diff_percent(previous_path, path)
                if change < self.settings.motion_detection_threshold:
                    snapshot_ts = now_utc_iso()
                    self.metrics.record_snapshot(snapshot_ts)
                    logger.info(
                        "Motion below threshold ({change:.2f}%), skipping {path}",
                        change=change,
                        path=str(path),
                    )
                    self._mark_processed(path, snapshot_ts)
                    return

            snapshot_ts = now_utc_iso()
            self.metrics.record_snapshot(snapshot_ts)

            groq_text, groq_latency, groq_usage = self._describe_with_groq(path, snapshot_ts)
            tags = {}
            if groq_text:
                tags = self._extract_tags(groq_text, snapshot_ts)
                self._write_description(path, snapshot_ts, groq_text, groq_latency, tags)

            if groq_usage:
                record_usage(
                    self.settings,
                    "groq",
                    self.settings.groq_model,
                    groq_usage,
                    "description",
                )

            self._compare_recent(path)
            self._mark_processed(path, snapshot_ts)

    def _describe_with_groq(self, path: Path, snapshot_ts: str) -> tuple[Optional[str], float, dict]:
        def _request():
            mime, data = encode_image(path)
            messages = prompts.groq_description_messages(snapshot_ts)
            payload = {
                "model": self.settings.groq_model,
                "messages": [
                    messages[0],
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": messages[1]["content"]},
                            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}},
                        ],
                    },
                ],
            }
            headers = {"Authorization": f"Bearer {self.settings.groq_api_key}"}
            with httpx.Client(timeout=60) as client:
                resp = client.post(f"{GROQ_BASE_URL}/chat/completions", json=payload, headers=headers)
                resp.raise_for_status()
                return resp.json()

        result, latency, error = _call_with_retry(
            self.groq_limiter,
            "groq",
            self.settings.api_retry_max_attempts,
            _request,
        )
        if error or not result:
            self.metrics.last_groq_failure = snapshot_ts
            self.metrics.record_api_call("groq", False, latency)
            return None, 0.0, {}

        text = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        usage = _extract_openai_usage(result)
        if not text:
            self.metrics.last_groq_failure = snapshot_ts
            self.metrics.record_api_call("groq", False, latency)
            return None, 0.0, usage
        self.metrics.last_groq_success = snapshot_ts
        self.metrics.record_api_call("groq", True, latency)
        return text, latency, usage

    def _extract_tags(self, description_text: str, snapshot_ts: str) -> dict[str, list[str]]:
        if not self.settings.tagging_enabled:
            return {"people": [], "vehicles": [], "objects": []}

        def _request():
            messages = prompts.groq_tag_messages(description_text)
            payload = {
                "model": self.settings.groq_model,
                "messages": messages,
            }
            headers = {"Authorization": f"Bearer {self.settings.groq_api_key}"}
            with httpx.Client(timeout=30) as client:
                resp = client.post(f"{GROQ_BASE_URL}/chat/completions", json=payload, headers=headers)
                resp.raise_for_status()
                return resp.json()

        result, latency, error = _call_with_retry(
            self.groq_limiter,
            "groq",
            self.settings.api_retry_max_attempts,
            _request,
        )
        if error or not result:
            self.metrics.last_groq_failure = snapshot_ts
            self.metrics.record_api_call("groq", False, latency)
            return {"people": [], "vehicles": [], "objects": []}

        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        usage = _extract_openai_usage(result)
        if usage:
            record_usage(
                self.settings,
                "groq",
                self.settings.groq_model,
                usage,
                "tags",
            )
        self.metrics.last_groq_success = snapshot_ts
        self.metrics.record_api_call("groq", True, latency)
        data = _extract_json_object(content)
        return _normalize_tags(data)

    def _compare_recent(self, path: Path) -> None:
        snapshots = storage.list_snapshot_files(self.settings.snapshots_dir)
        if len(snapshots) < 2:
            return
        latest_two = snapshots[-2:]
        if latest_two[1] != path:
            latest_two = [latest_two[0], path]
        first, second = latest_two
        self._compare_images(first, second, "10-minute")

    def compare_hourly(self) -> None:
        snapshots = storage.list_snapshot_files(self.settings.snapshots_dir)
        if len(snapshots) < 2:
            return
        latest = snapshots[-1]
        latest_ts = _parse_snapshot_time(latest, self.settings)
        if latest_ts is None:
            return
        target = latest_ts - timedelta(hours=1)
        candidate = _find_nearest_snapshot(snapshots, target, self.settings)
        if candidate is None:
            return
        self._compare_images(candidate, latest, "hourly")

    def compare_custom(self, path_a: Path, path_b: Path) -> dict:
        text, latency, usage = self._run_gemini_compare(path_a, path_b, "custom")
        timestamp = now_utc_iso()
        if not text:
            return {
                "timestamp": timestamp,
                "text": "",
                "error": "compare_failed",
            }
        record = {
            "timestamp": timestamp,
            "snapshot_a": _relative_path(path_a, self.settings.data_dir),
            "snapshot_b": _relative_path(path_b, self.settings.data_dir),
            "text": safe_truncate(text, 200),
            "provider": "gemini",
            "model": self.settings.google_model,
            "prompt_version": prompts.PROMPT_VERSION,
            "latency_ms": round(latency, 2),
        }
        storage.append_record(self.settings.data_dir, "compare_custom", record)
        if usage:
            record_usage(
                self.settings,
                "gemini",
                self.settings.google_model,
                usage,
                "compare_custom",
            )
        return record

    def ask_feed(self, query: str, lookback_hours: int, max_items: int) -> dict:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
        items = _filter_descriptions(self.settings, cutoff)
        if not items:
            return {
                "timestamp": now_utc_iso(),
                "answer": f"No snapshots in the last {lookback_hours} hours.",
                "window": {"lookback_hours": lookback_hours, "items": 0},
            }

        context, used_items, window_label, tags_summary = _build_ask_context(
            items,
            self.settings,
            max_items,
        )
        if not context:
            return {
                "timestamp": now_utc_iso(),
                "answer": "No descriptions available in the selected window.",
                "window": {"lookback_hours": lookback_hours, "items": 0},
            }

        text, latency, usage = self._run_gemini_ask(query, window_label, tags_summary, context)
        timestamp = now_utc_iso()
        if not text:
            self.metrics.last_gemini_failure = timestamp
            self.metrics.record_api_call("gemini", False, latency)
            return {
                "timestamp": timestamp,
                "answer": "",
                "error": "ask_failed",
            }

        self.metrics.last_gemini_success = timestamp
        self.metrics.record_api_call("gemini", True, latency)
        answer = safe_truncate(text, 400)
        if usage:
            record_usage(
                self.settings,
                "gemini",
                self.settings.google_model,
                usage,
                "ask",
            )
        return {
            "timestamp": timestamp,
            "answer": answer,
            "window": {
                "label": window_label,
                "lookback_hours": lookback_hours,
                "items": used_items,
            },
        }

    def daily_report(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        recent = storage.fetch_records_since(self.settings.data_dir, "compare_hourly", cutoff)
        if not recent:
            return

        tag_items = _filter_descriptions(self.settings, cutoff)
        tags_summary = _aggregate_tags(tag_items)
        tags_summary_text = _format_tags_summary(tags_summary)

        summary_text, highlights, usage = self._daily_summary(recent, tags_summary_text)
        if not summary_text:
            return
        timestamp = now_utc_iso()
        local_label = local_timestamp(self.settings).strftime("%Y-%m-%d")
        report = {
            "timestamp": timestamp,
            "date": local_label,
            "summary": summary_text,
            "text": summary_text,
            "highlights": highlights,
            "tags": tags_summary,
            "provider": "gemini",
            "model": self.settings.google_model,
            "prompt_version": prompts.PROMPT_VERSION,
        }
        output_path = self.settings.daily_reports_dir / f"{local_label}.json"
        storage.atomic_write_json(output_path, report)
        storage.append_record(self.settings.data_dir, "daily_reports", report)

        if usage:
            record_usage(
                self.settings,
                "gemini",
                self.settings.google_model,
                usage,
                "daily_report",
            )

    def _compare_images(self, path_a: Path, path_b: Path, label: str) -> None:
        text, latency, usage = self._run_gemini_compare(path_a, path_b, label)
        timestamp = now_utc_iso()
        if not text:
            self.metrics.last_gemini_failure = timestamp
            self.metrics.record_api_call("gemini", False, latency)
            return
        if len(text) > 200:
            logger.info("Truncating Gemini compare output to 200 chars")
        text = safe_truncate(text, 200)
        self.metrics.last_gemini_success = timestamp
        self.metrics.record_api_call("gemini", True, latency)

        record = {
            "timestamp": timestamp,
            "snapshot_a": _relative_path(path_a, self.settings.data_dir),
            "snapshot_b": _relative_path(path_b, self.settings.data_dir),
            "text": text,
            "provider": "gemini",
            "model": self.settings.google_model,
            "prompt_version": prompts.PROMPT_VERSION,
            "latency_ms": round(latency, 2),
        }
        out_dir = self.settings.compare_10m_dir if label == "10-minute" else self.settings.compare_hourly_dir
        out_path = _json_path_for_snapshot(path_b, self.settings.snapshots_dir, out_dir)
        storage.atomic_write_json(out_path, record)
        list_name = "compare_10m" if label == "10-minute" else "compare_hourly"
        storage.append_record(self.settings.data_dir, list_name, record)

        if usage:
            record_usage(
                self.settings,
                "gemini",
                self.settings.google_model,
                usage,
                f"compare_{label}",
            )

    def _run_gemini_compare(self, path_a: Path, path_b: Path, label: str) -> tuple[str, float, dict]:
        def _request():
            mime_a, data_a = encode_image(path_a)
            mime_b, data_b = encode_image(path_b)
            ts_a = _snapshot_label(path_a, self.settings)
            ts_b = _snapshot_label(path_b, self.settings)
            system, user = prompts.gemini_compare_prompt(ts_a, ts_b, label)
            payload = {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {"text": user},
                            {"inline_data": {"mime_type": mime_a, "data": data_a}},
                            {"inline_data": {"mime_type": mime_b, "data": data_b}},
                        ],
                    }
                ],
                "generationConfig": {"temperature": 0.2},
            }
            url = f"{GEMINI_BASE_URL}/models/{self.settings.google_model}:generateContent"
            with httpx.Client(timeout=60) as client:
                resp = client.post(url, params={"key": self.settings.google_api_key}, json=payload)
                resp.raise_for_status()
                return resp.json()

        result, latency, error = _call_with_retry(
            self.gemini_limiter,
            "gemini",
            self.settings.api_retry_max_attempts,
            _request,
        )
        if error or not result:
            return "", 0.0, {}
        text = _extract_gemini_text(result)
        usage = _extract_gemini_usage(result)
        return text, latency, usage

    def _run_gemini_ask(
        self,
        query: str,
        window_label: str,
        tags_summary: str,
        context: str,
    ) -> tuple[str, float, dict]:
        def _request():
            system, user = prompts.gemini_ask_prompt(query, window_label, tags_summary, context)
            payload = {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": user}],
                    }
                ],
                "generationConfig": {"temperature": 0.2},
            }
            url = f"{GEMINI_BASE_URL}/models/{self.settings.google_model}:generateContent"
            with httpx.Client(timeout=60) as client:
                resp = client.post(url, params={"key": self.settings.google_api_key}, json=payload)
                resp.raise_for_status()
                return resp.json()

        result, latency, error = _call_with_retry(
            self.gemini_limiter,
            "gemini",
            self.settings.api_retry_max_attempts,
            _request,
        )
        if error or not result:
            return "", 0.0, {}
        text = _extract_gemini_text(result)
        usage = _extract_gemini_usage(result)
        return text, latency, usage

    def _daily_summary(self, items: list[dict], tags_summary_text: str) -> tuple[str, list[str], dict]:
        def _request():
            date_label = local_timestamp(self.settings).strftime("%Y-%m-%d")
            system, user = prompts.gemini_daily_prompt(date_label, tags_summary_text)
            content_lines = [item.get("text", "") for item in items if item.get("text")]
            text_block = "\n".join(content_lines)
            payload = {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {"text": user},
                            {"text": text_block},
                        ],
                    }
                ],
                "generationConfig": {"temperature": 0.2},
            }
            url = f"{GEMINI_BASE_URL}/models/{self.settings.google_model}:generateContent"
            with httpx.Client(timeout=60) as client:
                resp = client.post(url, params={"key": self.settings.google_api_key}, json=payload)
                resp.raise_for_status()
                return resp.json()

        result, latency, error = _call_with_retry(
            self.gemini_limiter,
            "gemini",
            self.settings.api_retry_max_attempts,
            _request,
        )
        if error or not result:
            return "", [], {}
        text = _extract_gemini_text(result)
        usage = _extract_gemini_usage(result)
        summary, highlights = _parse_daily_response(text)
        if len(summary) > 500:
            logger.info("Truncating Gemini daily report to 500 chars")
        summary = safe_truncate(summary, 500)
        highlights = [safe_truncate(item, 140) for item in highlights][:3]
        return summary, highlights, usage

    def _write_description(
        self,
        path: Path,
        timestamp: str,
        text: str,
        latency: float,
        tags: dict[str, list[str]],
    ) -> None:
        record = {
            "timestamp": timestamp,
            "snapshot": _relative_path(path, self.settings.data_dir),
            "text": text,
            "tags": tags,
            "provider": "groq",
            "model": self.settings.groq_model,
            "prompt_version": prompts.PROMPT_VERSION,
            "latency_ms": round(latency, 2),
        }
        out_path = _json_path_for_snapshot(path, self.settings.snapshots_dir, self.settings.descriptions_dir)
        storage.atomic_write_json(out_path, record)
        storage.append_record(self.settings.data_dir, "descriptions", record)

    def _mark_processed(self, path: Path, timestamp: str) -> None:
        self.last_processed_path = path
        storage.write_last_processed(
            self.settings.run_dir / "last_processed.json",
            {"timestamp": timestamp, "path": str(path)},
        )


def _parse_daily_response(text: str) -> tuple[str, list[str]]:
    data = _extract_json_object(text)
    if isinstance(data, dict):
        summary = data.get("summary")
        highlights = data.get("highlights")
        if isinstance(summary, str):
            cleaned = summary.strip()
            if isinstance(highlights, list):
                items = [str(item).strip() for item in highlights if str(item).strip()]
            else:
                items = []
            return cleaned, items
    return text.strip(), []


def _extract_gemini_text(payload: dict) -> str:
    candidates = payload.get("candidates", [])
    if not candidates:
        return ""
    parts = candidates[0].get("content", {}).get("parts", [])
    text_parts = [p.get("text", "") for p in parts if p.get("text")]
    return " ".join(text_parts).strip()


def _parse_iso(value: Optional[str]):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _filter_descriptions(settings, cutoff: datetime) -> list[dict]:
    return storage.fetch_records_since(settings.data_dir, "descriptions", cutoff)


def _aggregate_tags(items: list[dict]) -> dict[str, list[tuple[str, int]]]:
    counts = {
        "people": Counter(),
        "vehicles": Counter(),
        "objects": Counter(),
    }
    for item in items:
        tags = item.get("tags", {})
        for key in counts:
            values = tags.get(key, []) if isinstance(tags, dict) else []
            for value in values:
                if isinstance(value, str) and value.strip():
                    counts[key][value.strip().lower()] += 1
    return {
        key: counts[key].most_common(5)
        for key in counts
    }


def _relative_path(path: Path, data_dir: Path) -> str:
    try:
        return str(path.relative_to(data_dir)).replace("\\", "/")
    except ValueError:
        return str(path)


def _json_path_for_snapshot(snapshot_path: Path, snapshots_dir: Path, output_dir: Path) -> Path:
    rel = snapshot_path.relative_to(snapshots_dir)
    return output_dir / rel.with_suffix(".json")


def _snapshot_label(path: Path, settings) -> str:
    ts = _parse_snapshot_time(path, settings)
    if ts is None:
        return path.name
    local_dt = ts.astimezone(settings.tz)
    return local_dt.strftime("%Y-%m-%d %H:%M:%S %Z")


def _parse_snapshot_time(path: Path, settings) -> Optional[datetime]:
    try:
        parts = path.parts
        filename = path.stem
        year = int(parts[-4])
        month = int(parts[-3])
        day = int(parts[-2])
        hour = int(filename[0:2])
        minute = int(filename[2:4])
        second = int(filename[4:6])
        local_dt = settings.tz.localize(datetime(year, month, day, hour, minute, second))
        return local_dt.astimezone(timezone.utc)
    except (ValueError, IndexError):
        return None


def _find_nearest_snapshot(snapshots: list[Path], target: datetime, settings) -> Optional[Path]:
    best = None
    best_delta = None
    for path in snapshots:
        ts = _parse_snapshot_time(path, settings)
        if ts is None:
            continue
        delta = abs((ts - target).total_seconds())
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best = path
    if best_delta is not None and best_delta > 60 * 60 * 2:
        return None
    return best

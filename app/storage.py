import json
import os
import sqlite3
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

try:
    import fcntl  # type: ignore
except ImportError:  # pragma: no cover - windows fallback
    fcntl = None

try:
    import msvcrt  # type: ignore
except ImportError:  # pragma: no cover - linux fallback
    msvcrt = None

_SNAPSHOT_CACHE_TTL_SEC = 2.0
_snapshot_cache_lock = threading.Lock()
_snapshot_cache_root: Optional[Path] = None
_snapshot_cache_ts = 0.0
_snapshot_cache_files: list[Path] = []

_RECORD_DB_NAME = "records.db"
_RECORD_LISTS = {
    "descriptions": "descriptions.json",
    "compare_10m": "compare_10m.json",
    "compare_hourly": "compare_hourly.json",
    "compare_custom": "compare_custom.json",
    "daily_reports": "daily_reports.json",
    "usage": "usage.json",
}
_record_lock = threading.Lock()
_migrated_record_lists: set[tuple[str, str]] = set()



def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


@contextmanager
def file_lock(lock_path: Path):
    ensure_dir(lock_path.parent)
    with open(lock_path, "a+", encoding="utf-8") as lock_file:
        if fcntl is not None:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        elif msvcrt is not None:
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            elif msvcrt is not None:
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)


def atomic_write_json(path: Path, data: Any) -> None:
    ensure_dir(path.parent)
    tmp_file = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(path.parent),
            delete=False,
        ) as tmp_file:
            json.dump(data, tmp_file, ensure_ascii=True, indent=2)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        os.replace(tmp_file.name, path)
    finally:
        if tmp_file is not None and os.path.exists(tmp_file.name):
            try:
                os.remove(tmp_file.name)
            except OSError:
                pass


def atomic_write_text(path: Path, data: str) -> None:
    ensure_dir(path.parent)
    tmp_file = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(path.parent),
            delete=False,
        ) as tmp_file:
            tmp_file.write(data)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        os.replace(tmp_file.name, path)
    finally:
        if tmp_file is not None and os.path.exists(tmp_file.name):
            try:
                os.remove(tmp_file.name)
            except OSError:
                pass


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default


def append_json_list(
    path: Path,
    item: dict,
    schema_validator: Optional[Callable[[dict], None]] = None,
) -> None:
    lock_path = path.with_suffix(path.suffix + ".lock")
    with file_lock(lock_path):
        data = read_json(path, [])
        if not isinstance(data, list):
            data = []
        if schema_validator is not None:
            schema_validator(item)
        data.append(item)
        atomic_write_json(path, data)


def write_json_list(
    path: Path,
    items: Iterable[dict],
    schema_validator: Optional[Callable[[dict], None]] = None,
) -> None:
    if schema_validator is not None:
        for entry in items:
            schema_validator(entry)
    atomic_write_json(path, list(items))


def list_snapshot_files(root: Path) -> list[Path]:
    global _snapshot_cache_root, _snapshot_cache_ts, _snapshot_cache_files
    now = time.time()
    with _snapshot_cache_lock:
        if (
            _snapshot_cache_root == root
            and now - _snapshot_cache_ts < _SNAPSHOT_CACHE_TTL_SEC
        ):
            return list(_snapshot_cache_files)
    if not root.exists():
        return []
    files = [p for p in root.rglob('*.jpg') if p.is_file()]
    files.extend([p for p in root.rglob('*.jpeg') if p.is_file()])
    files.extend([p for p in root.rglob('*.png') if p.is_file()])
    files = [p for p in files if not p.name.endswith('.tmp')]
    files.sort(key=lambda p: p.stat().st_mtime)
    with _snapshot_cache_lock:
        _snapshot_cache_root = root
        _snapshot_cache_ts = now
        _snapshot_cache_files = files
    return list(files)

def write_schema_version(data_dir: Path, version: str) -> None:
    version_path = data_dir / "schema_version.txt"
    if version_path.exists():
        return
    atomic_write_text(version_path, version)


def read_schema_version(data_dir: Path) -> Optional[str]:
    version_path = data_dir / "schema_version.txt"
    if not version_path.exists():
        return None
    try:
        return version_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def read_last_processed(path: Path) -> dict:
    return read_json(path, {})


def write_last_processed(path: Path, data: dict) -> None:
    atomic_write_json(path, data)

def _record_db_path(data_dir: Path) -> Path:
    return data_dir / _RECORD_DB_NAME


def _init_record_db(data_dir: Path) -> Path:
    db_path = _record_db_path(data_dir)
    ensure_dir(db_path.parent)
    with sqlite3.connect(str(db_path), timeout=30) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS records ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "list_name TEXT NOT NULL, "
            "timestamp TEXT, "
            "timestamp_epoch REAL, "
            "data TEXT NOT NULL"
            ")"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_records_list_id ON records (list_name, id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_records_list_ts ON records (list_name, timestamp_epoch)"
        )
    return db_path


def _parse_iso_epoch(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.timestamp()
    except ValueError:
        return None


def _maybe_migrate_record_list(data_dir: Path, list_name: str) -> None:
    if list_name not in _RECORD_LISTS:
        return
    db_path = _init_record_db(data_dir)
    key = (str(db_path), list_name)
    with _record_lock:
        if key in _migrated_record_lists:
            return
        _migrated_record_lists.add(key)
    json_path = data_dir / _RECORD_LISTS[list_name]
    if not json_path.exists():
        return
    with sqlite3.connect(str(db_path), timeout=30) as conn:
        row = conn.execute(
            "SELECT 1 FROM records WHERE list_name = ? LIMIT 1",
            (list_name,),
        ).fetchone()
        if row:
            return
        items = read_json(json_path, [])
        if not isinstance(items, list) or not items:
            return
        rows = []
        for item in items:
            ts_value = None
            if isinstance(item, dict):
                ts_value = item.get("timestamp") or item.get("ts")
            ts_epoch = _parse_iso_epoch(ts_value) if ts_value else None
            try:
                payload = json.dumps(item, ensure_ascii=True)
            except TypeError:
                continue
            rows.append((list_name, ts_value, ts_epoch, payload))
        if rows:
            conn.executemany(
                "INSERT INTO records (list_name, timestamp, timestamp_epoch, data) VALUES (?, ?, ?, ?)",
                rows,
            )


def append_record(
    data_dir: Path,
    list_name: str,
    item: dict,
    schema_validator: Optional[Callable[[dict], None]] = None,
) -> None:
    if schema_validator is not None:
        schema_validator(item)
    _maybe_migrate_record_list(data_dir, list_name)
    db_path = _init_record_db(data_dir)
    ts_value = item.get("timestamp") or item.get("ts")
    ts_epoch = _parse_iso_epoch(ts_value) if ts_value else None
    payload = json.dumps(item, ensure_ascii=True)
    with sqlite3.connect(str(db_path), timeout=30) as conn:
        conn.execute(
            "INSERT INTO records (list_name, timestamp, timestamp_epoch, data) VALUES (?, ?, ?, ?)",
            (list_name, ts_value, ts_epoch, payload),
        )


def fetch_records(
    data_dir: Path,
    list_name: str,
    limit: Optional[int] = None,
    offset: int = 0,
    newest_first: bool = False,
) -> list[dict]:
    _maybe_migrate_record_list(data_dir, list_name)
    db_path = _init_record_db(data_dir)
    order = "DESC" if newest_first else "ASC"
    query = "SELECT data FROM records WHERE list_name = ? ORDER BY id " + order
    params = [list_name]
    if limit is not None:
        query += " LIMIT ? OFFSET ?"
        params.extend([max(0, limit), max(0, offset)])
    elif offset:
        query += " LIMIT -1 OFFSET ?"
        params.append(max(0, offset))
    with sqlite3.connect(str(db_path), timeout=30) as conn:
        rows = conn.execute(query, params).fetchall()
    items = []
    for (payload,) in rows:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            items.append(data)
    return items


def fetch_records_since(
    data_dir: Path,
    list_name: str,
    cutoff: datetime,
) -> list[dict]:
    _maybe_migrate_record_list(data_dir, list_name)
    db_path = _init_record_db(data_dir)
    cutoff_epoch = cutoff.timestamp()
    query = (
        "SELECT data FROM records "
        "WHERE list_name = ? AND timestamp_epoch IS NOT NULL AND timestamp_epoch >= ? "
        "ORDER BY id ASC"
    )
    with sqlite3.connect(str(db_path), timeout=30) as conn:
        rows = conn.execute(query, (list_name, cutoff_epoch)).fetchall()
    items = []
    for (payload,) in rows:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            items.append(data)
    return items


def prune_records(
    data_dir: Path,
    list_name: str,
    cutoff: datetime,
    dry_run: bool = False,
) -> int:
    _maybe_migrate_record_list(data_dir, list_name)
    db_path = _init_record_db(data_dir)
    cutoff_epoch = cutoff.timestamp()
    with sqlite3.connect(str(db_path), timeout=30) as conn:
        if dry_run:
            row = conn.execute(
                "SELECT COUNT(*) FROM records "
                "WHERE list_name = ? AND timestamp_epoch IS NOT NULL AND timestamp_epoch < ?",
                (list_name, cutoff_epoch),
            ).fetchone()
            return int(row[0]) if row else 0
        cur = conn.execute(
            "DELETE FROM records "
            "WHERE list_name = ? AND timestamp_epoch IS NOT NULL AND timestamp_epoch < ?",
            (list_name, cutoff_epoch),
        )
        return cur.rowcount

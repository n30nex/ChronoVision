import json
import os
import tempfile
import threading
import time
from contextlib import contextmanager
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

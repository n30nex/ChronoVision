import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from loguru import logger

from . import storage


def cleanup(settings, dry_run: bool = False, archive: bool = False) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.retention_days)
    snapshots = storage.list_snapshot_files(settings.snapshots_dir)
    snapshots_sorted = sorted(snapshots, key=lambda p: p.stat().st_mtime)

    keep = set(snapshots_sorted[-settings.retention_min_snapshots :])
    for path in snapshots_sorted:
        snapshot_time = _parse_snapshot_time(path, settings)
        if path in keep:
            continue
        if snapshot_time and snapshot_time > cutoff:
            continue
        _remove_path(path, settings, dry_run, archive)

    _prune_json_list(settings.data_dir / "descriptions.json", cutoff, dry_run)
    _prune_json_list(settings.data_dir / "compare_10m.json", cutoff, dry_run)
    _prune_json_list(settings.data_dir / "compare_hourly.json", cutoff, dry_run)
    _prune_json_list(settings.data_dir / "daily_reports.json", cutoff, dry_run)
    _prune_json_list(settings.data_dir / "usage.json", cutoff, dry_run)


def _remove_path(path: Path, settings, dry_run: bool, archive: bool) -> None:
    if dry_run:
        logger.info("Retention dry-run: would remove {path}", path=str(path))
        return
    if archive:
        archive_dir = settings.backups_dir / "retention"
        archive_dir.mkdir(parents=True, exist_ok=True)
        target = archive_dir / path.name
        shutil.move(str(path), str(target))
        logger.info("Archived {path} -> {target}", path=str(path), target=str(target))
        return
    try:
        path.unlink()
        logger.info("Removed {path}", path=str(path))
    except OSError as exc:
        logger.warning("Failed to remove {path}: {error}", path=str(path), error=str(exc))


def _prune_json_list(list_path: Path, cutoff: datetime, dry_run: bool) -> None:
    items = storage.read_json(list_path, [])
    if not isinstance(items, list):
        return
    kept = []
    for item in items:
        timestamp = item.get("timestamp") or item.get("ts")
        if not timestamp:
            kept.append(item)
            continue
        try:
            ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            kept.append(item)
            continue
        if ts >= cutoff:
            kept.append(item)
    if dry_run:
        logger.info("Retention dry-run: would prune {path} from {before} to {after}",
                    path=str(list_path), before=len(items), after=len(kept))
        return
    storage.write_json_list(list_path, kept)


def _parse_snapshot_time(path: Path, settings):
    try:
        parts = path.parts
        filename = path.stem
        year = int(parts[-4])
        month = int(parts[-3])
        day = int(parts[-2])
        hour = int(filename[0:2])
        minute = int(filename[2:4])
        second = int(filename[4:6])
        local_dt = settings.tz.localize(
            datetime(year, month, day, hour, minute, second)
        )
        return local_dt.astimezone(timezone.utc)
    except (ValueError, IndexError):
        return None

import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from loguru import logger

from . import storage


def cleanup(settings, dry_run: bool = False, archive: bool = False) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.retention_days)
    snapshots = storage.list_snapshot_files(settings.snapshots_dir)
    snapshots_sorted = sorted(snapshots, key=lambda p: p.stat().st_mtime)

    keep_count = max(settings.retention_min_snapshots, 0)
    keep = set(snapshots_sorted[-keep_count:]) if keep_count else set()
    for path in snapshots_sorted:
        snapshot_time = _parse_snapshot_time(path, settings)
        if path in keep:
            continue
        if snapshot_time and snapshot_time > cutoff:
            continue
        _remove_snapshot_bundle(path, settings, dry_run, archive)

    for list_name in [
        "descriptions",
        "compare_10m",
        "compare_hourly",
        "compare_custom",
        "daily_reports",
        "usage",
    ]:
        _prune_records_list(settings, list_name, cutoff, dry_run)


def _remove_path(path: Path, settings, dry_run: bool, archive: bool) -> None:
    if dry_run:
        logger.info("Retention dry-run: would remove {path}", path=str(path))
        return
    if archive:
        archive_dir = settings.backups_dir / "retention"
        try:
            relative_path = path.relative_to(settings.data_dir)
            target = archive_dir / relative_path
        except ValueError:
            target = archive_dir / path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(target))
        logger.info("Archived {path} -> {target}", path=str(path), target=str(target))
        return
    try:
        path.unlink()
        logger.info("Removed {path}", path=str(path))
    except OSError as exc:
        logger.warning("Failed to remove {path}: {error}", path=str(path), error=str(exc))


def _remove_snapshot_bundle(path: Path, settings, dry_run: bool, archive: bool) -> None:
    _remove_path(path, settings, dry_run, archive)
    try:
        relative = path.relative_to(settings.snapshots_dir)
    except ValueError:
        return
    json_relative = relative.with_suffix(".json")
    derived_paths = [
        settings.descriptions_dir / json_relative,
        settings.compare_10m_dir / json_relative,
        settings.compare_hourly_dir / json_relative,
    ]
    for derived in derived_paths:
        if derived.exists():
            _remove_path(derived, settings, dry_run, archive)


def _prune_records_list(settings, list_name: str, cutoff: datetime, dry_run: bool) -> None:
    removed = storage.prune_records(settings.data_dir, list_name, cutoff, dry_run=dry_run)
    if dry_run and removed:
        logger.info(
            "Retention dry-run: would prune {list_name}: {count} records",
            list_name=list_name,
            count=removed,
        )


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

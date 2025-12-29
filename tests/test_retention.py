from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytz

from app import retention, storage


def _write_snapshot(root, dt: datetime):
    rel_dir = dt.strftime("%Y/%m/%d")
    filename = dt.strftime("%H%M%S") + ".jpg"
    path = root / rel_dir / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"test")
    return path


def _write_derived(base_dir, relative_snapshot):
    json_path = base_dir / relative_snapshot.with_suffix(".json")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text("{}", encoding="utf-8")


def test_retention_removes_bundle_and_prunes_records(tmp_path):
    data_dir = tmp_path / "data"
    settings = SimpleNamespace(
        data_dir=data_dir,
        snapshots_dir=data_dir / "snapshots",
        descriptions_dir=data_dir / "descriptions",
        compare_10m_dir=data_dir / "compare_10m",
        compare_hourly_dir=data_dir / "compare_hourly",
        daily_reports_dir=data_dir / "daily_reports",
        backups_dir=data_dir / "backups",
        retention_days=1,
        retention_min_snapshots=0,
        tz=pytz.UTC,
    )

    now = datetime.now(timezone.utc)
    old_dt = now - timedelta(days=2)
    new_dt = now - timedelta(hours=1)

    old_snapshot = _write_snapshot(settings.snapshots_dir, old_dt)
    new_snapshot = _write_snapshot(settings.snapshots_dir, new_dt)

    for snapshot in (old_snapshot, new_snapshot):
        relative = snapshot.relative_to(settings.snapshots_dir)
        for base in (settings.descriptions_dir, settings.compare_10m_dir, settings.compare_hourly_dir):
            _write_derived(base, relative)

    storage.append_record(
        settings.data_dir,
        "descriptions",
        {"timestamp": old_dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")},
    )
    storage.append_record(
        settings.data_dir,
        "descriptions",
        {"timestamp": new_dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")},
    )

    retention.cleanup(settings)

    assert not old_snapshot.exists()
    assert new_snapshot.exists()

    old_relative = old_snapshot.relative_to(settings.snapshots_dir).with_suffix(".json")
    new_relative = new_snapshot.relative_to(settings.snapshots_dir).with_suffix(".json")
    assert not (settings.descriptions_dir / old_relative).exists()
    assert (settings.descriptions_dir / new_relative).exists()

    remaining = storage.fetch_records(settings.data_dir, "descriptions")
    assert len(remaining) == 1

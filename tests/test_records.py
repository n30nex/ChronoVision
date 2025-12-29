import threading
from datetime import datetime, timedelta, timezone

from app import storage


def _iso(ts: datetime) -> str:
    return ts.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def test_append_and_fetch_records(tmp_path):
    now = datetime.now(timezone.utc)
    record_a = {"timestamp": _iso(now - timedelta(minutes=2)), "text": "first"}
    record_b = {"timestamp": _iso(now - timedelta(minutes=1)), "text": "second"}

    storage.append_record(tmp_path, "descriptions", record_a)
    storage.append_record(tmp_path, "descriptions", record_b)

    all_records = storage.fetch_records(tmp_path, "descriptions")
    assert [record["text"] for record in all_records] == ["first", "second"]

    latest = storage.fetch_records(tmp_path, "descriptions", limit=1, newest_first=True)
    assert latest[0]["text"] == "second"


def test_prune_records(tmp_path):
    now = datetime.now(timezone.utc)
    old = {"timestamp": _iso(now - timedelta(days=2)), "text": "old"}
    recent = {"timestamp": _iso(now), "text": "new"}

    storage.append_record(tmp_path, "usage", old)
    storage.append_record(tmp_path, "usage", recent)

    removed = storage.prune_records(tmp_path, "usage", now - timedelta(days=1))
    assert removed == 1

    remaining = storage.fetch_records(tmp_path, "usage")
    assert len(remaining) == 1
    assert remaining[0]["text"] == "new"


def test_concurrent_appends_are_resilient(tmp_path):
    now = datetime.now(timezone.utc)
    barrier = threading.Barrier(6)
    errors: list[BaseException] = []

    def worker(index: int) -> None:
        try:
            barrier.wait(timeout=5)
            record = {"timestamp": _iso(now + timedelta(seconds=index)), "text": f"t{index}"}
            storage.append_record(tmp_path, "usage", record)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors
    records = storage.fetch_records(tmp_path, "usage")
    assert len(records) == 6

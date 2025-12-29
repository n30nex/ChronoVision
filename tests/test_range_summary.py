from datetime import datetime, timedelta, timezone
import importlib

from fastapi.testclient import TestClient


def _load_app(monkeypatch, tmp_path):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setenv("GOOGLE_API_KEY", "test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CAMERA_SOURCE", "windows-host")
    monkeypatch.setenv("API_KEY", "")

    from app import main as main_module

    importlib.reload(main_module)
    main_module.app.router.on_startup.clear()
    main_module.app.router.on_shutdown.clear()
    return main_module


def test_range_summary_success(monkeypatch, tmp_path):
    main_module = _load_app(monkeypatch, tmp_path)
    main_module.runner.summarize_range = lambda start, end, max_items: {
        "timestamp": "2025-01-01T00:00:00Z",
        "answer": "ok",
        "window": {"label": "range", "start": start.isoformat(), "end": end.isoformat()},
    }
    client = TestClient(main_module.app)

    start = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=1)
    response = client.post(
        "/api/summary/range",
        json={"start": start.isoformat().replace("+00:00", "Z"), "end": end.isoformat().replace("+00:00", "Z")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"] == "ok"


def test_range_summary_requires_ordered_times(monkeypatch, tmp_path):
    main_module = _load_app(monkeypatch, tmp_path)
    client = TestClient(main_module.app)

    start = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
    end = start - timedelta(minutes=5)
    response = client.post(
        "/api/summary/range",
        json={"start": start.isoformat().replace("+00:00", "Z"), "end": end.isoformat().replace("+00:00", "Z")},
    )
    assert response.status_code == 400

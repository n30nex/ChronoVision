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


def test_story_daily_endpoint(monkeypatch, tmp_path):
    main_module = _load_app(monkeypatch, tmp_path)
    main_module.runner.story_arc = lambda hours, max_items: {
        "timestamp": "2025-01-01T00:00:00Z",
        "bullets": ["10:00 change detected"],
        "window": {"label": "range", "items": 1},
    }
    client = TestClient(main_module.app)
    response = client.get("/api/story/daily")
    assert response.status_code == 200
    payload = response.json()
    assert payload["bullets"]


def test_highlights_daily_endpoint(monkeypatch, tmp_path):
    main_module = _load_app(monkeypatch, tmp_path)
    main_module.runner.highlight_reel = lambda hours, max_items: {
        "timestamp": "2025-01-01T00:00:00Z",
        "items": [{"timestamp": "2025-01-01T00:00:00Z", "snapshot": "snapshots/x.jpg"}],
        "window": {"label": "range", "items": 1},
    }
    client = TestClient(main_module.app)
    response = client.get("/api/highlights/daily")
    assert response.status_code == 200
    payload = response.json()
    assert payload["items"]

import importlib

from fastapi.testclient import TestClient


def _load_app(monkeypatch, tmp_path, api_key: str):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setenv("GOOGLE_API_KEY", "test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("API_KEY", api_key)
    monkeypatch.setenv("CAMERA_SOURCE", "windows-host")

    from app import main as main_module

    importlib.reload(main_module)
    main_module.app.router.on_startup.clear()
    main_module.app.router.on_shutdown.clear()
    return main_module.app


def test_api_key_required(monkeypatch, tmp_path):
    app = _load_app(monkeypatch, tmp_path, "secret")
    client = TestClient(app)

    response = client.get("/api/health")
    assert response.status_code == 401

    response = client.get("/api/health", headers={"X-API-Key": "secret"})
    assert response.status_code == 200

    response = client.get("/api/health?api_key=secret")
    assert response.status_code == 200

import os

import pytest

from app.config import load_settings


def test_load_settings_valid(tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setenv("GOOGLE_API_KEY", "test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CAMERA_SOURCE", "windows-host")
    settings = load_settings()
    assert settings.data_dir == tmp_path
    assert settings.camera_source == "windows-host"


def test_load_settings_invalid_source(tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setenv("GOOGLE_API_KEY", "test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CAMERA_SOURCE", "invalid")
    with pytest.raises(ValueError):
        load_settings()

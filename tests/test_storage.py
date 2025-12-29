from app import storage


def test_atomic_write_json(tmp_path):
    path = tmp_path / "sample.json"
    storage.atomic_write_json(path, {"value": 123})
    data = storage.read_json(path, {})
    assert data["value"] == 123


def test_append_json_list(tmp_path):
    path = tmp_path / "list.json"
    storage.append_json_list(path, {"a": 1})
    storage.append_json_list(path, {"b": 2})
    data = storage.read_json(path, [])
    assert len(data) == 2

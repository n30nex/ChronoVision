from app.tasks import safe_truncate


def test_safe_truncate_short():
    text = "Short sentence."
    assert safe_truncate(text, 200) == "Short sentence."


def test_safe_truncate_long():
    text = "One sentence. Two sentence. Three sentence. Four sentence."
    result = safe_truncate(text, 20)
    assert len(result) <= 20

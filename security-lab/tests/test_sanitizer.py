from security.sanitizer import sanitize_prompt


def test_strips_null():
    out = sanitize_prompt("a\x00b", 100)
    assert "\x00" not in out
    assert "a" in out and "b" in out


def test_truncates():
    out = sanitize_prompt("x" * 1000, 10)
    assert len(out) == 10

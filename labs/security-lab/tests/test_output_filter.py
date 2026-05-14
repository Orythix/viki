from security.output_filter import filter_output


def test_redacts_sk_pattern():
    t, changed = filter_output("here sk-123456789012345678901234567890")
    assert changed
    assert "sk-123456789012345678901234567890" not in t
    assert "REDACTED" in t


def test_plain_unchanged():
    t, changed = filter_output("hello world")
    assert not changed
    assert t == "hello world"

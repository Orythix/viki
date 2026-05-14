from security.sandbox_url import validate_http_target


def test_validate_http_target_allowlist() -> None:
    hosts = ["sandbox-demo", "127.0.0.1"]
    assert validate_http_target("http://sandbox-demo:8080/x", hosts)[0] is True
    assert validate_http_target("http://127.0.0.1:1/", hosts)[0] is True
    assert validate_http_target("http://evil.test/", hosts)[0] is False
    assert validate_http_target("file:///etc/passwd", hosts)[0] is False

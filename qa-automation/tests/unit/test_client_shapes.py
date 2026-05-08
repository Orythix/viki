"""
Unit tests — no running server. Validates request construction with mocks.

Why: CI proves framework logic; live tests prove environment wiring.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from qa_lab.client import SecurityLabClient
from qa_lab.config import Settings


def test_get_sends_lab_headers() -> None:
    settings = Settings(base_url="http://example.test", api_key="secret-key", role="researcher")
    client = SecurityLabClient(settings, timeout=5.0)
    fake_response = httpx.Response(200, json={"status": "ok"})

    mock_instance = MagicMock()
    mock_instance.__enter__ = MagicMock(return_value=mock_instance)
    mock_instance.__exit__ = MagicMock(return_value=False)
    mock_instance.get.return_value = fake_response

    with patch("qa_lab.client.httpx.Client", return_value=mock_instance):
        r = client.get("/health")

    assert r.status_code == 200
    mock_instance.get.assert_called_once()
    args, kwargs = mock_instance.get.call_args
    assert args[0] == "http://example.test/health"
    assert kwargs["headers"]["X-Lab-API-Key"] == "secret-key"
    assert kwargs["headers"]["X-Lab-Role"] == "researcher"
    assert kwargs["headers"]["Content-Type"] == "application/json"


def test_post_json_payload() -> None:
    settings = Settings(base_url="http://example.test", api_key="k")
    client = SecurityLabClient(settings, timeout=5.0)
    fake_response = httpx.Response(200, json={"ok": True})

    mock_instance = MagicMock()
    mock_instance.__enter__ = MagicMock(return_value=mock_instance)
    mock_instance.__exit__ = MagicMock(return_value=False)
    mock_instance.post.return_value = fake_response

    with patch("qa_lab.client.httpx.Client", return_value=mock_instance):
        r = client.post_json("/api/v1/security/classify", {"message": "hello"})

    assert r.status_code == 200
    mock_instance.post.assert_called_once()
    _, kwargs = mock_instance.post.call_args
    assert kwargs["json"] == {"message": "hello"}

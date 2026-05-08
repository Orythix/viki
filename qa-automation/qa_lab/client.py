"""
HTTP client for the AI Security Learning Lab API.

Design notes (why this shape):
- Single place for base URL, auth headers, timeouts → less copy-paste in tests.
- Returns httpx.Response so tests can assert status, json(), headers (flexible).
- No hidden retries here — teach explicit retry policy in Week 6+ if needed.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from qa_lab.config import Settings


class SecurityLabClient:
    def __init__(self, settings: Settings, timeout: float = 30.0) -> None:
        self._settings = settings
        self._timeout = timeout

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        h = {
            "X-Lab-API-Key": self._settings.api_key,
            "X-Lab-Role": self._settings.role,
            "Content-Type": "application/json",
        }
        if extra:
            h.update(extra)
        return h

    def get(self, path: str, *, params: Optional[Dict[str, Any]] = None) -> httpx.Response:
        url = f"{self._settings.base_url}{path}"
        with httpx.Client(timeout=self._timeout) as client:
            return client.get(url, headers=self._headers(), params=params)

    def post_json(self, path: str, body: Dict[str, Any]) -> httpx.Response:
        url = f"{self._settings.base_url}{path}"
        with httpx.Client(timeout=self._timeout) as client:
            return client.post(url, headers=self._headers(), json=body)

    def get_unauthenticated(self, path: str) -> httpx.Response:
        """For negative auth tests — no API key header."""
        url = f"{self._settings.base_url}{path}"
        with httpx.Client(timeout=self._timeout) as client:
            return client.get(url)

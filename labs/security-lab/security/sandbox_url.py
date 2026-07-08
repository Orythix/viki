"""
Sandbox URL policy helpers (defensive).

Purpose
-------
Centralize host/scheme checks for lab HTTP tools so tests and the FastAPI layer
share identical rules without importing the full app stack.

Risks / mitigations
-------------------
Same as ``tools_registry.http_get_sandbox``: never pass user-controlled URLs to
requests without this gate; keep allowlists minimal.
"""

from __future__ import annotations

from urllib.parse import urlparse


def validate_http_target(url: str, allowed_hosts: list[str]) -> tuple[bool, str]:
    """
    Returns (allowed, reason). ``allowed`` means the URL may be fetched under
    lab policy (still subject to RBAC and rate limits).
    """
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https"):
            return False, f"only http/https allowed, not {p.scheme!r}"
        host = (p.hostname or "").lower()
        if host not in {h.lower() for h in allowed_hosts}:
            return False, f"host not allowed: {host or '(empty)'}"
        return True, "ok"
    except Exception as e:
        return False, str(e)

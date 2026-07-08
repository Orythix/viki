"""
Output filtering — redact likely secrets from model text before returning to client.

Purpose: reduce accidental disclosure if the model echoes training or context secrets.

Risks: regex redaction misses novel formats; may redact benign text resembling secrets.

Mitigations: tune patterns; show user a "redacted" marker in audit log only, not inline by default.
"""

from __future__ import annotations

import re

_API_KEY_LIKE = re.compile(
    r"\b(sk-[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|"
    r"AIza[0-9A-Za-z_-]{35}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{20,})\b"
)
_HIGH_ENTROPY = re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b")  # may match base64


def filter_output(text: str, aggressive: bool = False) -> tuple[str, bool]:
    changed = False
    t = text
    if _API_KEY_LIKE.search(t):
        t = _API_KEY_LIKE.sub("[REDACTED_API_LIKE]", t)
        changed = True
    if aggressive and _HIGH_ENTROPY.search(t):
        t = _HIGH_ENTROPY.sub("[REDACTED_HIGH_ENTROPY]", t)
        changed = True
    return t, changed

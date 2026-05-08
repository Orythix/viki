"""
Input sanitization for untrusted chat and tool arguments.

Purpose: normalize text, enforce size limits, strip dangerous control characters.

Risks: over-sanitization can break valid Unicode; under-sanitization allows binary smuggling in edge cases.

Mitigations: explicit max length; allow printable Unicode; log truncation events.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def sanitize_prompt(text: str, max_chars: int) -> str:
    if not isinstance(text, str):
        raise TypeError("prompt must be str")
    # Remove NULL bytes and other C0 controls except common whitespace
    cleaned = []
    for ch in text:
        o = ord(ch)
        if o in (9, 10, 13):  # tab, lf, cr
            cleaned.append(ch)
        elif 32 <= o <= 0x10FFFF and o not in range(0x2028, 0x202F):  # keep most printable
            cleaned.append(ch)
        else:
            continue
    out = "".join(cleaned)
    if len(out) > max_chars:
        logger.info("prompt_truncated", extra={"extra_fields": {"from": len(out), "to": max_chars}})
        out = out[:max_chars]
    return out.strip()

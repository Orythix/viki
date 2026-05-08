"""Redact sensitive substrings from structured log payloads before persistence."""
from __future__ import annotations

import re
from typing import Any, Dict

_KEY_PATTERN = re.compile(r"(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*\S+", re.I)


def redact_mapping(data: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in data.items():
        if isinstance(v, str):
            out[k] = _KEY_PATTERN.sub(lambda m: m.group(1) + "=[REDACTED]", v)
        elif isinstance(v, dict):
            out[k] = redact_mapping(v)
        else:
            out[k] = v
    return out

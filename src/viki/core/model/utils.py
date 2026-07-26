"""Shared helper functions for model inference."""

from __future__ import annotations

import os
from typing import Any


def debug_enabled() -> bool:
    return os.environ.get("VIKI_DEBUG", "").lower() in ("true", "1", "yes")


def effective_profile_for_factory(
    profile: dict[str, Any],
    provider_conf: dict[str, Any],
    system_settings: dict[str, Any] | None,
) -> dict[str, Any]:
    return dict(profile)


def looks_like_openai_secret(key: str | None) -> bool:
    if not key or not str(key).strip():
        return False
    s = str(key).strip()
    lowered = s.lower()
    if lowered in (
        "none",
        "dummy",
        "placeholder",
        "test",
        "your-api-key-here",
        "changeme",
    ):
        return False
    return s.startswith("sk-")


def looks_like_anthropic_secret(key: str | None) -> bool:
    if not key or not str(key).strip():
        return False
    s = str(key).strip()
    lowered = s.lower()
    if lowered in (
        "none",
        "dummy",
        "placeholder",
        "test",
        "your-api-key-here",
        "changeme",
    ):
        return False
    return s.startswith("sk-ant-")

"""Shared helper functions for model inference."""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import Any


def debug_enabled() -> bool:
    return os.environ.get("VIKI_DEBUG", "").lower() in ("true", "1", "yes")


def resolve_ollama_thinking_from_settings(system_settings: dict[str, Any] | None) -> bool:
    env = (os.environ.get("VIKI_OLLAMA_THINK") or "").strip().lower()
    if env in ("1", "true", "yes"):
        return True
    if env in ("0", "false", "no"):
        return False
    sys = (system_settings or {}).get("system") or {}
    return bool(sys.get("ollama_enable_thinking", False))


def resolve_ollama_options_from_settings(system_settings: dict[str, Any] | None) -> dict[str, Any]:
    sys = (system_settings or {}).get("system") or {}
    opts = sys.get("ollama_options")
    return dict(opts) if isinstance(opts, dict) else {}


def effective_profile_for_factory(
    profile: dict[str, Any],
    provider_conf: dict[str, Any],
    system_settings: dict[str, Any] | None,
) -> dict[str, Any]:
    if provider_conf.get("type") != "local":
        return profile
    merged = dict(profile)
    thinking = resolve_ollama_thinking_from_settings(system_settings)
    if profile.get("ollama_enable_thinking") is not None:
        thinking = bool(profile["ollama_enable_thinking"])
    merged["ollama_enable_thinking"] = thinking
    base_opts = resolve_ollama_options_from_settings(system_settings)
    po = profile.get("ollama_options")
    if isinstance(po, dict):
        merged["ollama_options"] = {**base_opts, **po}
    elif base_opts:
        merged["ollama_options"] = dict(base_opts)
    return merged


def looks_like_openai_secret(key: str | None) -> bool:
    if not key or not str(key).strip():
        return False
    s = str(key).strip()
    lowered = s.lower()
    if lowered in (
        "ollama",
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
        "ollama",
        "none",
        "dummy",
        "placeholder",
        "test",
        "your-api-key-here",
        "changeme",
    ):
        return False
    return s.startswith("sk-ant-")


def ollama_model_exists(base_url: str, model_name: str) -> bool:
    try:
        req = urllib.request.Request(
            f"{base_url}/api/tags",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for m in data.get("models", []):
            if m.get("name") == model_name or m.get("model") == model_name:
                return True
    except Exception:
        logging.getLogger(__name__).warning("ollama_model_exists check failed")
    return False

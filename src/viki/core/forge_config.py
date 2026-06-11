"""Neural Forge: default Ollama image tag for prompt-bake / internal_forge."""

from __future__ import annotations

import os
from typing import Any

DEFAULT_FORGE_OUTPUT_OLLAMA_TAG = "viki-neural-forge"


def resolve_forge_output_ollama_tag(settings: dict[str, Any] | None = None) -> str:
    """Env VIKI_FORGE_OUTPUT_OLLAMA_MODEL, then system.forge_output_ollama_tag, then default."""
    env = (os.environ.get("VIKI_FORGE_OUTPUT_OLLAMA_MODEL") or "").strip()
    if env:
        return env
    if settings:
        sysconf = settings.get("system") or {}
        tag = (sysconf.get("forge_output_ollama_tag") or "").strip()
        if tag:
            return tag
    return DEFAULT_FORGE_OUTPUT_OLLAMA_TAG

"""Inference gateway — re-exports from model/ package.

This file exists for backward compatibility. New code should import
directly from ``viki.core.model``.
"""

from __future__ import annotations

from viki.core.model import (  # noqa: F401
    APILLM,
    FallbackLLM,
    LLMProvider,
    LocalLLM,
    ModelFactory,
    ModelRouter,
    StructuredPrompt,
)

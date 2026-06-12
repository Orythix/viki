"""Fallback LLM used when no configured model is available."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from .llm_provider import LLMProvider

T = Any


class FallbackLLM(LLMProvider):
    """Fallback LLM used when no configured model is available (dev/edge case)."""

    def is_cloud(self) -> bool:
        return False

    async def chat(self, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        t0 = time.perf_counter()
        success = False
        try:
            await asyncio.sleep(0.1)
            success = True
            return f"Fallback response for {self.model_name}"
        finally:
            try:
                from viki.core.usage_log import emit_llm_inference

                emit_llm_inference(self, time.perf_counter() - t0, success, "chat")
            except Exception:
                pass

    async def chat_structured(
        self,
        messages: list[dict[str, str]],
        response_model: type[T],
        temperature: float = 0.0,
        image_path: str = None,
    ) -> T:
        t0 = time.perf_counter()
        success = False
        try:
            await asyncio.sleep(0.1)
            success = True
            return response_model()
        finally:
            try:
                from viki.core.usage_log import emit_llm_inference

                emit_llm_inference(self, time.perf_counter() - t0, success, "chat_structured")
            except Exception:
                pass

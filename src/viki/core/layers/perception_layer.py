"""Layer 1: Input Normalization & Signal Detection."""

from __future__ import annotations

from viki.config.logger import viki_logger

from .cortex_layer import CortexLayer


class PerceptionLayer(CortexLayer):
    """Layer 1: Input Normalization & Signal Detection."""

    async def _logic(self, user_input: str) -> str:
        viki_logger.debug(f"Layer 1 (Perception) active for: {user_input[:50]}...")
        cleaned = " ".join(user_input.strip().split())
        return cleaned

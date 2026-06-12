"""Base class for all Orythix cognitive layers."""

from __future__ import annotations

from typing import Any

from viki.core.schema import LayerState


class CortexLayer:
    def __init__(self, name: str, description: str):
        self.state = LayerState(name=name)
        self.description = description

    async def process(self, input_data: Any) -> Any:
        self.state.status = "Processing"
        self.state.load = 50.0
        result = await self._logic(input_data)
        self.state.status = "Idle"
        self.state.load = 0.0
        return result

    async def _logic(self, data: Any) -> Any:
        raise NotImplementedError

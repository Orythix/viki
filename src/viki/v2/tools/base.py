"""BaseTool abstract class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..core.permission_manager import PermissionTier


@dataclass
class ToolResult:
    success: bool
    data: Any = None
    error: str | None = None
    error_type: str | None = None
    warnings: list[str] = field(default_factory=list)


class BaseTool(ABC):
    name: str = ""
    description: str = ""
    capabilities: list[str] = field(default_factory=list)
    permission_tier: PermissionTier = PermissionTier.SAFE
    examples: list[str] = field(default_factory=list)
    parameters: dict = field(default_factory=dict)

    @abstractmethod
    async def execute(self, params: dict, provider=None) -> ToolResult:
        ...

    def get_tool_definition(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self._build_llm_description(),
                "parameters": self.parameters,
            },
        }

    def _build_llm_description(self) -> str:
        caps = ", ".join(self.capabilities)
        exs = ", ".join(self.examples)
        return f"{self.description}\nCapabilities: {caps}\nExamples: {exs}\nRisk: {self.permission_tier.name}"

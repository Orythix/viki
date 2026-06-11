"""LLM-based tool selection from registry."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class ToolSelector:
    def __init__(self, tool_registry=None):
        self.tool_registry = tool_registry

    def get_tool_definitions(self) -> list[dict]:
        if not self.tool_registry:
            return []
        return self.tool_registry.get_tool_definitions()

    def select_tool(self, intent: str, context: str = "") -> tuple[str, dict] | None:
        if not self.tool_registry:
            return None

        intent_lower = intent.lower()

        for tool_name, tool in self.tool_registry._tools.items():
            for example in tool.examples:
                if any(word in intent_lower for word in example.lower().split()):
                    return tool_name, {}

            for cap in tool.capabilities:
                if any(word in intent_lower for word in cap.replace("_", " ").split()):
                    return tool_name, {}

        return None

"""Central tool registry."""

from __future__ import annotations

from collections import defaultdict

from .base import BaseTool, ToolResult


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
        self._categories: dict[str, list[str]] = defaultdict(list)

    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool
        for cap in tool.capabilities:
            self._categories[cap].append(tool.name)

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def get_tool_definitions(self) -> list[dict]:
        return [t.get_tool_definition() for t in self._tools.values()]

    async def execute(self, name: str, params: dict, **kwargs) -> ToolResult:
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(success=False, error=f"Unknown tool: {name}")
        try:
            return await tool.execute(params, **kwargs)
        except Exception as e:
            return ToolResult(success=False, error=str(e), error_type="execution_failed")

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

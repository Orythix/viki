"""LLM-based tool selection from registry."""

from __future__ import annotations

from typing import Any, cast

from ..llm import get_llm_client


class ToolSelector:
    """LLM-based tool selection — reads tool definitions and picks the best match."""

    def __init__(self, tool_registry=None):
        self.tool_registry = tool_registry
        self._llm = get_llm_client()

    def get_tool_definitions(self) -> list[dict]:
        """Return all tool definitions for LLM function calling."""
        if not self.tool_registry:
            return []
        return cast("list[dict[Any, Any]]", self.tool_registry.get_tool_definitions())

    def _format_tools_for_selection(self) -> str:
        """Format tools for LLM selection prompt."""
        if not self.tool_registry or not self.tool_registry._tools:
            return "No tools available"

        lines = []
        for tool in self.tool_registry._tools.values():
            lines.append(f"### {tool.name}")
            lines.append(f"Description: {tool.description}")
            if tool.capabilities:
                lines.append(f"Capabilities: {', '.join(tool.capabilities)}")
            if tool.examples:
                lines.append(f"Examples: {', '.join(tool.examples[:3])}")
            lines.append(f"Permission tier: {tool.permission_tier.name}")
            lines.append("")
        return "\n".join(lines)

    async def select_tool(self, intent: str, context: str = "") -> tuple[str, dict] | None:
        """Select the best tool for the given intent using LLM."""
        if not self.tool_registry or not self.tool_registry._tools:
            return None

        tool_descriptions = self._format_tools_for_selection()

        prompt = f"""You are a tool selection system. Choose the BEST tool for the user's intent.

Intent: {intent}
Context: {context}

Available tools:
{tool_descriptions}

Select ONE tool that best matches the intent. Consider:
- Does the tool's description match the intent?
- Do the tool's capabilities cover what the user needs?
- Do the examples resemble the user's request?

Respond in JSON:
{{
    "tool": "tool_name",
    "parameters": {{}},
    "reasoning": "why this tool was selected"
}}"""

        try:
            schema = {
                "type": "object",
                "properties": {
                    "tool": {"type": "string"},
                    "parameters": {"type": "object"},
                    "reasoning": {"type": "string"},
                },
                "required": ["tool", "parameters", "reasoning"],
            }
            result = await self._llm.structured_output(prompt, schema)
            tool_name = result.get("tool")
            if tool_name and tool_name in self.tool_registry._tools:
                return tool_name, result.get("parameters", {})
            return None
        except Exception:
            return None

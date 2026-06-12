"""LLM-based semantic intent classification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..llm import get_llm_client


@dataclass
class IntentResult:
    goal: str
    tool: str
    parameters: dict[str, Any]
    confidence: float
    requires_clarification: bool = False


class IntentAnalyzer:
    """
    LLM-based intent classification.
    No keyword lists, no regex patterns. Uses tool descriptions + examples.
    """

    def __init__(self, tool_registry=None):
        self.tool_registry = tool_registry
        self._llm = get_llm_client()

    def _format_tools_for_prompt(self) -> str:
        """Format available tools for the LLM prompt."""
        if not self.tool_registry:
            return "No tools available"

        lines = []
        for tool in self.tool_registry._tools.values():
            lines.append(f"## {tool.name}")
            lines.append(f"Description: {tool.description}")
            if tool.capabilities:
                lines.append(f"Capabilities: {', '.join(tool.capabilities)}")
            if tool.examples:
                lines.append(f"Example queries: {', '.join(tool.examples[:5])}")
            lines.append(f"Permission tier: {tool.permission_tier.name}")
            lines.append("")
        return "\n".join(lines)

    async def analyze(self, user_input: str) -> IntentResult | None:
        """Analyze user input and determine which tool(s) can fulfill it."""
        if not self.tool_registry or not self.tool_registry._tools:
            return None

        tool_descriptions = self._format_tools_for_prompt()

        prompt = f"""You are an intent analysis system for a local AI assistant.

Your job: analyze the user's request and determine which tool can fulfill it.

Rules:
- Do NOT match keywords — understand the semantic meaning
- Multiple phrasings should map to the same tool
- If uncertain, return requires_clarification: true
- Extract structured parameters from natural language

Available tools:
{tool_descriptions}

User request: {user_input}

Respond in JSON format with:
{{
    "goal": "one sentence describing user's goal",
    "tool": "tool_name",
    "parameters": {{}},
    "confidence": 0.0-1.0,
    "requires_clarification": false
}}"""

        try:
            schema = {
                "type": "object",
                "properties": {
                    "goal": {"type": "string"},
                    "tool": {"type": "string"},
                    "parameters": {"type": "object"},
                    "confidence": {"type": "number"},
                    "requires_clarification": {"type": "boolean"},
                },
                "required": ["goal", "tool", "parameters", "confidence", "requires_clarification"],
            }
            result = await self._llm.structured_output(prompt, schema)
            return IntentResult(**result)
        except Exception:
            return None

"""Builds LLM context from memory + tools — with cached system prompt and tool result truncation."""

from __future__ import annotations

from typing import Any

_MAX_OBSERVATION_CHARS = 4000


class ContextBuilder:
    """Builds the system prompt context for the LLM with caching."""

    def __init__(self, tool_registry=None, session_memory=None):
        self.tool_registry = tool_registry
        self.session_memory = session_memory
        self._cached_system_prompt: str | None = None

    def build_system_prompt(self) -> str:
        """Build (or return cached) system prompt with available tools."""
        if self._cached_system_prompt is not None:
            return self._cached_system_prompt

        tool_defs = ""
        if self.tool_registry:
            for tool in self.tool_registry._tools.values():
                tool_defs += f"- {tool.name}: {tool.description}\n"
                if tool.capabilities:
                    tool_defs += f"  Capabilities: {', '.join(tool.capabilities)}\n"
                if tool.examples:
                    tool_defs += f"  Examples: {', '.join(tool.examples[:3])}\n"

        self._cached_system_prompt = f"""You are VIKI, a local-first AI assistant with access to system tools.

You can use the following tools by calling them:
{tool_defs}

Rules:
1. Always reason before acting (ReAct: Thought -> Action -> Observation)
2. Use tools when you need information or need to perform actions
3. If a tool fails, try an alternative approach
4. Be concise and helpful
5. Never make up information — use tools to get facts

Available tool calling format:
{{"tool": "tool_name", "parameters": {{...}}}}

When you have enough information to answer, respond directly without tool calls."""
        return self._cached_system_prompt

    def invalidate_cache(self):
        """Clear cached system prompt (call after tool registry changes)."""
        self._cached_system_prompt = None

    def build_messages(self, user_input: str) -> list[dict[str, str]]:
        """Build messages for LLM including history."""
        messages = [{"role": "system", "content": self.build_system_prompt()}]

        if self.session_memory:
            for turn in self.session_memory.turns:
                messages.append({"role": "user", "content": turn.user})
                if turn.assistant:
                    messages.append({"role": "assistant", "content": turn.assistant})

        messages.append({"role": "user", "content": user_input})
        return messages

    def add_observation(self, messages: list[dict], tool_name: str, result: Any) -> list[dict]:
        """Add tool observation to message history (truncated)."""
        obs = str(result)
        if len(obs) > _MAX_OBSERVATION_CHARS:
            obs = obs[:_MAX_OBSERVATION_CHARS] + "\n... [truncated]"
        messages.append({"role": "user", "content": f"Tool '{tool_name}' returned: {obs}"})
        return messages

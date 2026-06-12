"""Session memory — in-memory conversation + state."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Turn:
    user: str
    assistant: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


class SessionMemory:
    """In-memory conversation and state for the current session."""

    def __init__(self, max_turns: int = 15):
        self.turns: list[Turn] = []
        self.max_turns = max_turns
        self.state: dict[str, Any] = {}
        self.pending_actions: list[dict] = []

    def add_turn(self, user: str, assistant: str = "", tool_calls: list[dict] | None = None):
        self.turns.append(Turn(user=user, assistant=assistant, tool_calls=tool_calls or []))
        if len(self.turns) > self.max_turns:
            self.turns.pop(0)

    def get_context(self, token_limit: int = 4096) -> list[dict]:
        """Return messages in LLM format, truncated to token limit."""
        messages = []
        total = 0
        for turn in reversed(self.turns):
            msgs = [{"role": "user", "content": turn.user}]
            if turn.assistant:
                msgs.append({"role": "assistant", "content": turn.assistant})
            # Rough token estimation: ~4 chars per token
            tokens = sum(len(m["content"]) // 4 for m in msgs)
            if total + tokens > token_limit:
                break
            messages = msgs + messages
            total += tokens
        return messages

    def set_state(self, key: str, value: Any):
        self.state[key] = value

    def get_state(self, key: str, default: Any = None) -> Any:
        return self.state.get(key, default)

    def add_pending_action(self, action: dict):
        self.pending_actions.append(action)

    def clear_pending(self):
        self.pending_actions.clear()

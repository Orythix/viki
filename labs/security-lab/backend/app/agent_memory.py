"""
Short-term session memory for the lab agent (educational).

Risks: memory poisoning — untrusted content stored as "facts" influences later prompts.

Mitigations: separate system vs user channels; cap message count; optional injection scan on retrieve;
do not auto-elevate user text to system prompts.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import Lock
from typing import Literal

Role = Literal["user", "assistant", "system"]


@dataclass
class Message:
    role: Role
    content: str


class SessionMemory:
    def __init__(self, max_messages: int = 40) -> None:
        self._sessions: dict[str, deque[Message]] = {}
        self._lock = Lock()
        self._max = max_messages

    def append(self, session_id: str, role: Role, content: str) -> None:
        with self._lock:
            q = self._sessions.setdefault(session_id, deque(maxlen=self._max))
            q.append(Message(role=role, content=content))

    def transcript(self, session_id: str) -> list[Message]:
        with self._lock:
            q = self._sessions.get(session_id)
            if not q:
                return []
            return list(q)

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

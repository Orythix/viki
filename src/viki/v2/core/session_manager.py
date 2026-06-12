"""Manages agent session lifecycle with TTL eviction."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field


@dataclass
class Turn:
    user: str
    assistant: str = ""
    tool_calls: list = field(default_factory=list)


class Session:
    def __init__(self):
        self.id = str(uuid.uuid4())
        self.created_at = time.time()
        self.last_active = self.created_at
        self.history: list[dict] = []
        self.turns: list[Turn] = []


class SessionManager:
    def __init__(self, ttl_minutes: int = 60):
        self._sessions: dict[str, Session] = {}
        self.ttl = ttl_minutes * 60

    def _evict_expired(self):
        """Remove sessions that have exceeded TTL."""
        now = time.time()
        expired = [sid for sid, s in self._sessions.items() if now - s.last_active > self.ttl]
        for sid in expired:
            del self._sessions[sid]

    def create_session(self) -> Session:
        s = Session()
        self._sessions[s.id] = s
        return s

    def get_or_create(self, session_id: str | None = None) -> Session:
        self._evict_expired()
        if session_id and session_id in self._sessions:
            return self._sessions[session_id]
        return self.create_session()

    def get_session(self, session_id: str) -> Session | None:
        self._evict_expired()
        return self._sessions.get(session_id)

    def delete_session(self, session_id: str):
        self._sessions.pop(session_id, None)

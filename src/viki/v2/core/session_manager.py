"""Manages agent session lifecycle."""

from __future__ import annotations

import time
import uuid


class Session:
    def __init__(self):
        self.id = str(uuid.uuid4())
        self.created_at = time.time()
        self.last_active = self.created_at
        self.history: list[dict] = []


class SessionManager:
    def __init__(self, ttl_minutes: int = 60):
        self._sessions: dict[str, Session] = {}
        self.ttl = ttl_minutes * 60

    def create_session(self) -> Session:
        s = Session()
        self._sessions[s.id] = s
        return s

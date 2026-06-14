"""Structured audit logging for Public Safety Skills Framework."""

from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from viki.skills.public_safety.base import InputValidator


class AuditEventType(Enum):
    SKILL_EXECUTION = "skill_execution"
    SAFETY_VIOLATION = "safety_violation"
    AUTHORIZATION_CHECK = "authorization_check"
    DATA_ACCESS = "data_access"
    AGENT_COORDINATION = "agent_coordination"
    ERROR = "error"
    CONFIG_CHANGE = "config_change"


class AuditSeverity(Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    event_type: AuditEventType = AuditEventType.SKILL_EXECUTION
    severity: AuditSeverity = AuditSeverity.INFO
    skill_name: str = ""
    action: str = ""
    actor: str = "system"
    session_id: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    sanitized_input: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "skill_name": self.skill_name,
            "action": self.action,
            "actor": self.actor,
            "session_id": self.session_id,
            "details": self.details,
            "result": self.result,
            "sanitized_input": self.sanitized_input,
        }


class AuditStore:
    """Persistent storage for audit events."""

    def __init__(self, storage_path: str | None = None):
        self._events: list[AuditEvent] = []
        self._callbacks: list[Callable[[AuditEvent], None]] = []
        self._storage_path = storage_path
        if storage_path:
            os.makedirs(storage_path, exist_ok=True)
            self._load()

    def add_callback(self, callback: Callable[[AuditEvent], None]):
        self._callbacks.append(callback)

    def record(self, event: AuditEvent):
        self._events.append(event)
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception:
                pass
        if self._storage_path:
            self._save()

    def create_event(
        self,
        event_type: AuditEventType,
        severity: AuditSeverity = AuditSeverity.INFO,
        skill_name: str = "",
        action: str = "",
        actor: str = "system",
        session_id: str = "",
        details: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
        raw_input: str | None = None,
    ) -> AuditEvent:
        sanitized = InputValidator.sanitize_for_logging(raw_input or "")
        event = AuditEvent(
            event_type=event_type,
            severity=severity,
            skill_name=skill_name,
            action=action,
            actor=actor,
            session_id=session_id,
            details=details or {},
            result=result,
            sanitized_input=sanitized,
        )
        self.record(event)
        return event

    def query(
        self,
        event_type: AuditEventType | None = None,
        skill_name: str | None = None,
        severity: AuditSeverity | None = None,
        actor: str | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        results = self._events
        if event_type:
            results = [e for e in results if e.event_type == event_type]
        if skill_name:
            results = [e for e in results if e.skill_name == skill_name]
        if severity:
            results = [e for e in results if e.severity == severity]
        if actor:
            results = [e for e in results if e.actor == actor]
        return results[-limit:]

    def get_recent(self, limit: int = 50) -> list[AuditEvent]:
        return self._events[-limit:]

    def get_safety_violations(self, limit: int = 50) -> list[AuditEvent]:
        return self.query(
            event_type=AuditEventType.SAFETY_VIOLATION,
            limit=limit,
        )

    def get_errors(self, limit: int = 50) -> list[AuditEvent]:
        return self.query(
            severity=AuditSeverity.ERROR,
            limit=limit,
        )

    def export_json(self, filepath: str):
        data = [e.to_dict() for e in self._events]
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

    def clear(self):
        self._events.clear()

    def _load(self):
        if not self._storage_path:
            return
        path = os.path.join(self._storage_path, "public_safety_audit.json")
        if not os.path.exists(path):
            return
        try:
            with open(path) as f:
                data = json.load(f)
            for entry in data:
                entry["event_type"] = AuditEventType(entry["event_type"])
                entry["severity"] = AuditSeverity(entry["severity"])
                self._events.append(AuditEvent(**entry))
        except Exception:
            pass

    def _save(self):
        if not self._storage_path:
            return
        path = os.path.join(self._storage_path, "public_safety_audit.json")
        try:
            with open(path, "w") as f:
                json.dump([e.to_dict() for e in self._events], f, indent=2)
        except Exception:
            pass


class AuditContextManager:
    """Context manager for tracking skill execution in audit logs."""

    def __init__(
        self,
        store: AuditStore,
        skill_name: str,
        action: str,
        actor: str = "system",
        session_id: str = "",
    ):
        self.store = store
        self.skill_name = skill_name
        self.action = action
        self.actor = actor
        self.session_id = session_id
        self.event: AuditEvent | None = None
        self._start_time: float = 0.0

    async def __aenter__(self):
        self._start_time = time.time()
        self.event = self.store.create_event(
            event_type=AuditEventType.SKILL_EXECUTION,
            severity=AuditSeverity.INFO,
            skill_name=self.skill_name,
            action=self.action,
            actor=self.actor,
            session_id=self.session_id,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        elapsed = (time.time() - self._start_time) * 1000
        if exc_type is not None:
            self.event.severity = AuditSeverity.ERROR
            self.event.result = {
                "success": False,
                "error": str(exc_val),
                "execution_time_ms": round(elapsed, 2),
            }
        else:
            self.event.result = {
                "success": True,
                "execution_time_ms": round(elapsed, 2),
            }
        self.store.record(self.event)

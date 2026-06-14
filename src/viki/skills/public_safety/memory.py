"""Memory system for Public Safety Skills Framework."""

from __future__ import annotations

import enum
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


class MemoryType(enum.Enum):
    SHORT_TERM = "short_term"
    WORKING = "working"
    LONG_TERM = "long_term"
    CASE_MEMORY = "case_memory"


@dataclass
class MemoryEntry:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: MemoryType = MemoryType.SHORT_TERM
    content: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    source: str = ""
    confidence: float = 1.0
    timestamp: float = field(default_factory=time.time)
    ttl_seconds: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        if self.ttl_seconds is None:
            return False
        return (time.time() - self.timestamp) > self.ttl_seconds

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "content": self.content,
            "tags": self.tags,
            "source": self.source,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "ttl_seconds": self.ttl_seconds,
            "metadata": self.metadata,
        }


class PublicSafetyMemory:
    """Thread-safe memory store for cases, requests, and research."""

    def __init__(self, storage_path: str | None = None):
        self._short_term: list[MemoryEntry] = []
        self._working: dict[str, MemoryEntry] = {}
        self._long_term: list[MemoryEntry] = []
        self._cases: dict[str, list[MemoryEntry]] = {}
        self._storage_path = storage_path
        if storage_path:
            os.makedirs(storage_path, exist_ok=True)
            self._load()

    def store(self, entry: MemoryEntry):
        if entry.type == MemoryType.SHORT_TERM:
            self._short_term.append(entry)
            self._prune_short_term()
        elif entry.type == MemoryType.WORKING:
            self._working[entry.id] = entry
        elif entry.type == MemoryType.LONG_TERM:
            self._long_term.append(entry)
        elif entry.type == MemoryType.CASE_MEMORY:
            case_id = entry.metadata.get("case_id", "default")
            self._cases.setdefault(case_id, []).append(entry)
        if self._storage_path:
            self._save()

    def get(self, memory_id: str) -> MemoryEntry | None:
        for entry in self._short_term:
            if entry.id == memory_id and not entry.is_expired():
                return entry
        entry = self._working.get(memory_id)
        if entry and not entry.is_expired():
            return entry
        for entry in self._long_term:
            if entry.id == memory_id:
                return entry
        for entries in self._cases.values():
            for entry in entries:
                if entry.id == memory_id:
                    return entry
        return None

    def search(self, query: str, max_results: int = 10) -> list[MemoryEntry]:
        query_lower = query.lower()
        results: list[tuple[MemoryEntry, int]] = []

        all_entries: list[MemoryEntry] = []
        all_entries.extend(e for e in self._short_term if not e.is_expired())
        all_entries.extend(e for e in self._working.values() if not e.is_expired())
        all_entries.extend(self._long_term)
        for entries in self._cases.values():
            all_entries.extend(entries)

        for entry in all_entries:
            score = 0
            content_str = json.dumps(entry.content).lower()
            if query_lower in content_str:
                score += 3
            for tag in entry.tags:
                if query_lower in tag.lower():
                    score += 2
            if query_lower in entry.source.lower():
                score += 1
            if score > 0:
                results.append((entry, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return [r[0] for r in results[:max_results]]

    def get_case(self, case_id: str) -> list[MemoryEntry]:
        return self._cases.get(case_id, [])

    def get_working_memory(self) -> dict[str, MemoryEntry]:
        return {k: v for k, v in self._working.items() if not v.is_expired()}

    def get_recent(self, limit: int = 20) -> list[MemoryEntry]:
        all_entries: list[MemoryEntry] = []
        all_entries.extend(e for e in self._short_term if not e.is_expired())
        all_entries.extend(e for e in self._working.values() if not e.is_expired())
        all_entries.extend(self._long_term)
        all_entries.sort(key=lambda e: e.timestamp, reverse=True)
        return all_entries[:limit]

    def clear_short_term(self):
        self._short_term.clear()

    def clear_working(self):
        self._working.clear()

    def clear_case(self, case_id: str):
        self._cases.pop(case_id, None)

    def _prune_short_term(self, max_entries: int = 100):
        self._short_term = [e for e in self._short_term if not e.is_expired()]
        if len(self._short_term) > max_entries:
            self._short_term.sort(key=lambda e: e.timestamp, reverse=True)
            self._short_term = self._short_term[:max_entries]

    def _load(self):
        if not self._storage_path:
            return
        path = os.path.join(self._storage_path, "public_safety_memory.json")
        if not os.path.exists(path):
            return
        try:
            with open(path) as f:
                data = json.load(f)
            for entry_data in data.get("short_term", []):
                entry_data["type"] = MemoryType(entry_data["type"])
                self._short_term.append(MemoryEntry(**entry_data))
            for entry_data in data.get("working", []):
                entry_data["type"] = MemoryType(entry_data["type"])
                self._working[entry_data["id"]] = MemoryEntry(**entry_data)
            for entry_data in data.get("long_term", []):
                entry_data["type"] = MemoryType(entry_data["type"])
                self._long_term.append(MemoryEntry(**entry_data))
            for case_id, entries in data.get("cases", {}).items():
                for entry_data in entries:
                    entry_data["type"] = MemoryType(entry_data["type"])
                    self._cases.setdefault(case_id, []).append(MemoryEntry(**entry_data))
        except Exception:
            pass

    def _save(self):
        if not self._storage_path:
            return
        path = os.path.join(self._storage_path, "public_safety_memory.json")
        try:
            data = {
                "short_term": [e.to_dict() for e in self._short_term],
                "working": [e.to_dict() for e in self._working.values()],
                "long_term": [e.to_dict() for e in self._long_term],
                "cases": {
                    cid: [e.to_dict() for e in entries] for cid, entries in self._cases.items()
                },
            }
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

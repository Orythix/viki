"""Auto-learning system for VIKI Safety & Public Safety Skills.

Learns from threat patterns, updates detection rules, stores experiences,
and enables continuous improvement without manual updates.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LearnedPattern:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    pattern_type: str = ""
    trigger: str = ""
    action: str = ""
    confidence: float = 0.0
    success_count: int = 0
    fail_count: int = 0
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    source: str = ""

    @property
    def reliability(self) -> float:
        total = self.success_count + self.fail_count
        if total == 0:
            return 0.0
        return self.success_count / total

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "pattern_type": self.pattern_type,
            "trigger": self.trigger,
            "action": self.action,
            "confidence": self.confidence,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "reliability": self.reliability,
            "created_at": self.created_at,
            "last_used": self.last_used,
            "source": self.source,
        }


@dataclass
class ThreatMemory:
    """A recorded threat incident that the system learned from."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    threat_summary: str = ""
    threat_type: str = ""
    risk_level: str = "low"
    evidence_patterns: list[str] = field(default_factory=list)
    detection_success: bool = True
    feedback_score: float = 0.0
    timestamp: float = field(default_factory=time.time)
    lesson_learned: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "threat_summary": self.threat_summary,
            "threat_type": self.threat_type,
            "risk_level": self.risk_level,
            "evidence_patterns": self.evidence_patterns,
            "detection_success": self.detection_success,
            "feedback_score": self.feedback_score,
            "timestamp": self.timestamp,
            "lesson_learned": self.lesson_learned,
        }


class AutoLearningEngine:
    """Self-contained auto-learning engine for VIKI Safety.

    Stores threat patterns, learns from new encounters, and adapts
    detection rules over time. Works standalone or can sync with
    VIKIController's LearningModule.
    """

    def __init__(self, data_dir: str | None = None):
        self._enabled = True
        self._data_dir = data_dir or os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..",
            "..",
            "..",
            "..",
            "data",
            "safety_learning",
        )
        os.makedirs(self._data_dir, exist_ok=True)

        self._patterns: dict[str, LearnedPattern] = {}
        self._threat_memories: list[ThreatMemory] = []
        self._pattern_stats: dict[str, dict[str, int]] = defaultdict(
            lambda: {"seen": 0, "blocked": 0, "missed": 0}
        )

        self._controller_learning = None
        self._db_path = os.path.join(self._data_dir, "safety_learning.db")
        self._init_db()
        self._load()

    def connect_controller(self, controller_learning):
        """Connect to VIKIController's LearningModule for synced learning."""
        self._controller_learning = controller_learning

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self):
        self._enabled = True

    def disable(self):
        self._enabled = False

    # --- Pattern Learning ---

    def learn_pattern(
        self,
        trigger: str,
        pattern_type: str = "threat_signature",
        action: str = "alert",
        confidence: float = 0.5,
        source: str = "viki_safety",
    ) -> LearnedPattern:
        """Learn a new detection pattern from an observed threat."""
        if not self._enabled:
            return LearnedPattern()

        existing = self._find_pattern(trigger, pattern_type)
        if existing:
            existing.confidence = min(1.0, existing.confidence + 0.05)
            existing.success_count += 1
            existing.last_used = time.time()
            self._save_pattern(existing)
            return existing

        pattern = LearnedPattern(
            pattern_type=pattern_type,
            trigger=trigger.lower().strip(),
            action=action,
            confidence=confidence,
            success_count=1,
            source=source,
        )
        self._patterns[pattern.id] = pattern
        self._save_pattern(pattern)
        return pattern

    def record_outcome(self, pattern_id: str, success: bool):
        """Record whether a learned pattern led to a correct detection."""
        pattern = self._patterns.get(pattern_id)
        if not pattern:
            return

        if success:
            pattern.success_count += 1
            pattern.confidence = min(1.0, pattern.confidence + 0.05)
        else:
            pattern.fail_count += 1
            pattern.confidence = max(0.1, pattern.confidence - 0.1)
        pattern.last_used = time.time()

        self._db_execute(
            "UPDATE learned_patterns SET success_count=?, fail_count=?, confidence=?, last_used=? WHERE id=?",
            (
                pattern.success_count,
                pattern.fail_count,
                pattern.confidence,
                pattern.last_used,
                pattern_id,
            ),
        )

    def get_reliable_patterns(self, min_reliability: float = 0.7) -> list[LearnedPattern]:
        """Get patterns that have proven reliable over time."""
        return [
            p
            for p in self._patterns.values()
            if p.reliability >= min_reliability and p.success_count >= 3
        ]

    def get_patterns_by_type(self, pattern_type: str) -> list[LearnedPattern]:
        return [p for p in self._patterns.values() if p.pattern_type == pattern_type]

    def suggest_new_patterns(self) -> list[dict[str, Any]]:
        """Analyze threat memories and suggest new patterns to learn."""
        suggestions = []
        type_counts: dict[str, int] = defaultdict(int)
        risk_counts: dict[str, int] = defaultdict(int)

        for mem in self._threat_memories:
            type_counts[mem.threat_type] += 1
            risk_counts[mem.risk_level] += 1

        for threat_type, count in type_counts.items():
            if count >= 3:
                suggestions.append(
                    {
                        "suggestion": f"Frequent threat type '{threat_type}' ({count} incidents) — consider proactive monitoring",
                        "pattern_type": threat_type,
                        "incident_count": count,
                        "action": "add_monitoring_rule",
                    }
                )

        return suggestions

    # --- Threat Memory ---

    def remember_threat(
        self,
        summary: str,
        threat_type: str,
        risk_level: str,
        evidence_patterns: list[str] | None = None,
        detection_success: bool = True,
    ) -> ThreatMemory:
        """Store a threat incident for future learning."""
        mem = ThreatMemory(
            threat_summary=summary,
            threat_type=threat_type,
            risk_level=risk_level,
            evidence_patterns=evidence_patterns or [],
            detection_success=detection_success,
        )
        self._threat_memories.append(mem)
        self._pattern_stats[threat_type]["seen"] += 1
        if detection_success:
            self._pattern_stats[threat_type]["blocked"] += 1
        else:
            self._pattern_stats[threat_type]["missed"] += 1

        self._db_execute(
            "INSERT INTO threat_memories (id, threat_summary, threat_type, risk_level, evidence_patterns, detection_success, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                mem.id,
                summary,
                threat_type,
                risk_level,
                json.dumps(evidence_patterns or []),
                1 if detection_success else 0,
                mem.timestamp,
            ),
        )

        if self._controller_learning:
            try:
                self._controller_learning.save_lesson(
                    trigger=f"Threat detected: {threat_type}",
                    fact=f"VIKI Safety detected {threat_type} threat (risk: {risk_level}): {summary[:200]}",
                    source=f"viki_safety/{threat_type}",
                )
            except Exception:
                pass

        if evidence_patterns:
            for pattern in evidence_patterns:
                self.learn_pattern(
                    trigger=pattern,
                    pattern_type=f"threat_indicator_{threat_type}",
                    source=f"viki_safety/{threat_type}",
                )

        return mem

    def get_recent_threats(self, limit: int = 50) -> list[ThreatMemory]:
        return sorted(self._threat_memories, key=lambda m: m.timestamp, reverse=True)[:limit]

    def get_threats_by_type(self, threat_type: str) -> list[ThreatMemory]:
        return [m for m in self._threat_memories if m.threat_type == threat_type]

    def get_statistics(self) -> dict[str, Any]:
        """Get learning statistics and insights."""
        total_patterns = len(self._patterns)
        reliable = len(self.get_reliable_patterns())
        total_threats = len(self._threat_memories)
        recent = self.get_recent_threats(10)

        return {
            "enabled": self._enabled,
            "patterns_learned": total_patterns,
            "reliable_patterns": reliable,
            "threats_recorded": total_threats,
            "recent_threats": [m.to_dict() for m in recent],
            "pattern_stats": dict(self._pattern_stats),
            "suggestions": self.suggest_new_patterns(),
            "learning_rate": round(reliable / max(total_patterns, 1), 2),
        }

    # --- Internal ---

    def _find_pattern(self, trigger: str, pattern_type: str) -> LearnedPattern | None:
        trigger_lower = trigger.lower().strip()
        for p in self._patterns.values():
            if p.trigger == trigger_lower and p.pattern_type == pattern_type:
                return p
        return None

    def _init_db(self):
        self._db_conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._db_conn.execute("PRAGMA journal_mode=WAL")
        self._db_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS learned_patterns (
                id TEXT PRIMARY KEY,
                pattern_type TEXT,
                trigger TEXT,
                action TEXT,
                confidence REAL,
                success_count INTEGER,
                fail_count INTEGER,
                created_at REAL,
                last_used REAL,
                source TEXT
            )
        """
        )
        self._db_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS threat_memories (
                id TEXT PRIMARY KEY,
                threat_summary TEXT,
                threat_type TEXT,
                risk_level TEXT,
                evidence_patterns TEXT,
                detection_success INTEGER,
                feedback_score REAL,
                timestamp REAL,
                lesson_learned TEXT
            )
        """
        )
        self._db_conn.commit()

    def _db_execute(self, sql: str, params: tuple = ()):
        try:
            self._db_conn.execute(sql, params)
            self._db_conn.commit()
        except Exception:
            pass

    def _save_pattern(self, pattern: LearnedPattern):
        self._db_execute(
            """INSERT OR REPLACE INTO learned_patterns
            (id, pattern_type, trigger, action, confidence, success_count, fail_count, created_at, last_used, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                pattern.id,
                pattern.pattern_type,
                pattern.trigger,
                pattern.action,
                pattern.confidence,
                pattern.success_count,
                pattern.fail_count,
                pattern.created_at,
                pattern.last_used,
                pattern.source,
            ),
        )

    def _load(self):
        try:
            rows = self._db_conn.execute("SELECT * FROM learned_patterns").fetchall()
            for row in rows:
                self._patterns[row[0]] = LearnedPattern(
                    id=row[0],
                    pattern_type=row[1],
                    trigger=row[2],
                    action=row[3],
                    confidence=row[4],
                    success_count=row[5],
                    fail_count=row[6],
                    created_at=row[7],
                    last_used=row[8],
                    source=row[9],
                )
        except Exception:
            pass

        try:
            rows = self._db_conn.execute(
                "SELECT * FROM threat_memories ORDER BY timestamp DESC LIMIT 1000"
            ).fetchall()
            for row in rows:
                patterns = json.loads(row[4]) if row[4] else []
                self._threat_memories.append(
                    ThreatMemory(
                        id=row[0],
                        threat_summary=row[1],
                        threat_type=row[2],
                        risk_level=row[3],
                        evidence_patterns=patterns,
                        detection_success=bool(row[5]),
                        feedback_score=row[6] or 0.0,
                        timestamp=row[7],
                        lesson_learned=row[8] or "",
                    )
                )
        except Exception:
            pass

    def close(self):
        try:
            self._db_conn.close()
        except Exception:
            pass


# Global singleton for easy access across the safety system
_auto_learning_engine: AutoLearningEngine | None = None


def get_auto_learning_engine(data_dir: str | None = None) -> AutoLearningEngine:
    global _auto_learning_engine
    if _auto_learning_engine is None:
        _auto_learning_engine = AutoLearningEngine(data_dir)
    return _auto_learning_engine

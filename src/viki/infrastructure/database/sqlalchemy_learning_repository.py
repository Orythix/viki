"""
SQLite-backed learning repository (pure sqlite3 — no SQLAlchemy dependency).

Replaces the original SQLAlchemy implementation so this module actually
imports without extra dependencies.  Implements ``ILearningRepository``
using the same sqlite3 patterns as ``LearningModule``.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time

from viki.domain.entities.learning import FailureRecord, Lesson, Relationship
from viki.domain.interfaces.learning_repository import ILearningRepository

_log = logging.getLogger("viki.repository")


class SqlAlchemyLearningRepository(ILearningRepository):
    """Pure-sqlite3 implementation of ILearningRepository.

    Despite the historical name, this has zero dependency on SQLAlchemy.
    """

    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """CREATE TABLE IF NOT EXISTS lessons (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                text_representation TEXT NOT NULL,
                embedding TEXT,
                created_at REAL NOT NULL,
                last_accessed REAL NOT NULL,
                access_count INTEGER DEFAULT 1,
                author TEXT NOT NULL,
                source_task TEXT NOT NULL,
                reliability REAL NOT NULL DEFAULT 1.0
            )"""
        )
        cur.execute(
            """CREATE TABLE IF NOT EXISTS failures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                error TEXT NOT NULL,
                context TEXT NOT NULL,
                timestamp REAL NOT NULL
            )"""
        )
        cur.execute(
            """CREATE TABLE IF NOT EXISTS relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                type TEXT NOT NULL,
                weight REAL NOT NULL DEFAULT 1.0,
                metadata_json TEXT,
                FOREIGN KEY(source_id) REFERENCES lessons(id),
                FOREIGN KEY(target_id) REFERENCES lessons(id)
            )"""
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_rel_source ON relationships(source_id)")
        self.conn.commit()

    def _row_to_lesson(self, row: sqlite3.Row) -> Lesson:
        return Lesson(
            id=row["id"],
            content=row["content"],
            text_representation=row["text_representation"],
            embedding=json.loads(row["embedding"]) if row["embedding"] else None,
            created_at=row["created_at"],
            last_accessed=row["last_accessed"],
            access_count=row["access_count"],
            author=row["author"],
            source_task=row["source_task"],
            reliability=row["reliability"],
        )

    def save_lesson(self, lesson: Lesson) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO lessons
               (id, content, text_representation, embedding,
                created_at, last_accessed, access_count, author,
                source_task, reliability)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                lesson.id,
                lesson.content,
                lesson.text_representation,
                json.dumps(lesson.embedding) if lesson.embedding else None,
                lesson.created_at or time.time(),
                lesson.last_accessed or time.time(),
                lesson.access_count,
                lesson.author,
                lesson.source_task,
                lesson.reliability,
            ),
        )
        self.conn.commit()

    def get_lesson(self, lesson_id: str) -> Lesson | None:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,))
        row = cur.fetchone()
        if row is None:
            return None
        return self._row_to_lesson(row)

    def get_relevant_lessons(self, query: str = "", limit: int = 5) -> list[Lesson]:
        cur = self.conn.cursor()
        if query:
            pattern = f"%{query}%"
            cur.execute(
                """SELECT * FROM lessons
                   WHERE text_representation LIKE ?
                   ORDER BY last_accessed DESC LIMIT ?""",
                (pattern, limit),
            )
        else:
            cur.execute("SELECT * FROM lessons ORDER BY last_accessed DESC LIMIT ?", (limit,))
        return [self._row_to_lesson(r) for r in cur.fetchall()]

    def save_failure(self, failure: FailureRecord) -> None:
        self.conn.execute(
            "INSERT INTO failures (action, error, context, timestamp) VALUES (?, ?, ?, ?)",
            (failure.action, failure.error, failure.context, failure.timestamp or time.time()),
        )
        self.conn.commit()

    def get_relevant_failures(self, query: str = "", limit: int = 5) -> list[FailureRecord]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM failures ORDER BY timestamp DESC LIMIT ?", (limit,))
        return [
            FailureRecord(
                id=r["id"],
                action=r["action"],
                error=r["error"],
                context=r["context"],
                timestamp=r["timestamp"],
            )
            for r in cur.fetchall()
        ]

    def save_relationship(self, relationship: Relationship) -> None:
        self.conn.execute(
            """INSERT INTO relationships (source_id, target_id, type, weight, metadata_json)
               VALUES (?, ?, ?, ?, ?)""",
            (
                relationship.source_id,
                relationship.target_id,
                relationship.type,
                relationship.weight,
                json.dumps(relationship.metadata),
            ),
        )
        self.conn.commit()

    def get_related_concepts(self, lesson_id: str) -> list[Lesson]:
        cur = self.conn.cursor()
        cur.execute(
            """SELECT l.* FROM lessons l
               JOIN relationships r ON r.target_id = l.id
               WHERE r.source_id = ?
               UNION
               SELECT l.* FROM lessons l
               JOIN relationships r ON r.source_id = l.id
               WHERE r.target_id = ?""",
            (lesson_id, lesson_id),
        )
        return [self._row_to_lesson(r) for r in cur.fetchall()]

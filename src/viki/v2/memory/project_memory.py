"""Project memory — persistent project context (SQLite) — async via thread pool."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ProjectInfo:
    path: str
    name: str
    language: str | None
    framework: str | None
    detected_at: float


@dataclass
class Decision:
    topic: str
    decision: str
    reasoning: str
    created_at: float


class ProjectMemory:
    """Persistent project context stored in SQLite — async via thread pool.

    All SQLite operations are offloaded to a thread pool to avoid blocking
    the asyncio event loop. A single persistent connection with a threading
    lock ensures thread safety.
    """

    def __init__(self, db_path: str | None = None):
        if db_path is None:
            data_dir = os.environ.get("VIKI_DATA_DIR", "./data")
            Path(data_dir).mkdir(parents=True, exist_ok=True)
            db_path = str(Path(data_dir) / "project_memory.db")
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        with self._lock:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS active_project (
                    id INTEGER PRIMARY KEY,
                    path TEXT UNIQUE,
                    name TEXT,
                    language TEXT,
                    framework TEXT,
                    detected_at REAL
                );
                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY,
                    topic TEXT,
                    decision TEXT,
                    reasoning TEXT,
                    created_at REAL
                );
                CREATE TABLE IF NOT EXISTS project_context (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at REAL
                );
                CREATE TABLE IF NOT EXISTS open_tasks (
                    id INTEGER PRIMARY KEY,
                    title TEXT,
                    description TEXT,
                    status TEXT,
                    created_at REAL,
                    updated_at REAL
                );
            """
            )
            conn.commit()
        self._conn = conn

    async def set_active_project(self, path: str):
        """Record the currently active project."""
        path = str(Path(path).resolve())

        def _detect():
            p = Path(path)
            name = p.name
            language = None
            framework = None
            if (p / "pyproject.toml").exists() or (p / "requirements.txt").exists():
                language = "Python"
            elif (p / "package.json").exists():
                language = "JavaScript/TypeScript"
            elif (p / "Cargo.toml").exists():
                language = "Rust"
            elif (p / "go.mod").exists():
                language = "Go"
            return (name, language, framework)

        name, language, framework = await asyncio.to_thread(_detect)

        def _save():
            with self._lock:
                self._conn.execute(
                    """
                    INSERT OR REPLACE INTO active_project
                    (path, name, language, framework, detected_at)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (path, name, language, framework, time.time()),
                )
                self._conn.commit()

        await asyncio.to_thread(_save)

    async def get_active_project(self) -> ProjectInfo | None:
        def _():
            with self._lock:
                row = self._conn.execute(
                    """
                    SELECT path, name, language, framework, detected_at
                    FROM active_project
                    ORDER BY detected_at DESC LIMIT 1
                """
                ).fetchone()
                if row:
                    return ProjectInfo(**dict(row))
                return None

        return await asyncio.to_thread(_)

    async def record_decision(self, topic: str, decision: str, reasoning: str):
        """Store architectural decisions for context continuity."""

        def _():
            with self._lock:
                self._conn.execute(
                    """
                    INSERT INTO decisions (topic, decision, reasoning, created_at)
                    VALUES (?, ?, ?, ?)
                """,
                    (topic, decision, reasoning, time.time()),
                )
                self._conn.commit()

        await asyncio.to_thread(_)

    async def get_recent_decisions(self, limit: int = 5) -> list[Decision]:
        def _():
            with self._lock:
                rows = self._conn.execute(
                    """
                    SELECT topic, decision, reasoning, created_at
                    FROM decisions ORDER BY created_at DESC LIMIT ?
                """,
                    (limit,),
                ).fetchall()
                return [Decision(**dict(r)) for r in rows]

        return await asyncio.to_thread(_)

    async def set_context(self, key: str, value: Any):
        """Store arbitrary project context."""

        def _():
            with self._lock:
                self._conn.execute(
                    """
                    INSERT OR REPLACE INTO project_context (key, value, updated_at)
                    VALUES (?, ?, ?)
                """,
                    (key, json.dumps(value), time.time()),
                )
                self._conn.commit()

        await asyncio.to_thread(_)

    async def get_context(self, key: str, default: Any = None) -> Any:
        def _():
            with self._lock:
                row = self._conn.execute(
                    "SELECT value FROM project_context WHERE key = ?", (key,)
                ).fetchone()
                if row:
                    return json.loads(row["value"])
                return default

        return await asyncio.to_thread(_)

    async def add_task(self, title: str, description: str = "") -> int:
        def _():
            with self._lock:
                cur = self._conn.execute(
                    """
                    INSERT INTO open_tasks (title, description, status, created_at, updated_at)
                    VALUES (?, ?, 'open', ?, ?)
                """,
                    (title, description, time.time(), time.time()),
                )
                self._conn.commit()
                return cur.lastrowid

        return await asyncio.to_thread(_)

    async def update_task(self, task_id: int, status: str | None = None, **kwargs):
        def _():
            with self._lock:
                if status:
                    self._conn.execute(
                        "UPDATE open_tasks SET status = ?, updated_at = ? WHERE id = ?",
                        (status, time.time(), task_id),
                    )
                self._conn.commit()

        await asyncio.to_thread(_)

    async def get_tasks(self, status: str | None = None) -> list[dict]:
        def _():
            with self._lock:
                if status:
                    rows = self._conn.execute(
                        "SELECT * FROM open_tasks WHERE status = ? ORDER BY created_at DESC",
                        (status,),
                    ).fetchall()
                else:
                    rows = self._conn.execute(
                        "SELECT * FROM open_tasks ORDER BY created_at DESC"
                    ).fetchall()
                return [dict(r) for r in rows]

        return await asyncio.to_thread(_)

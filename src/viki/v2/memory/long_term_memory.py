"""Long-term memory — preferences, patterns, knowledge (SQLite + vector) — async via thread pool."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Optional embedding support — graceful degradation if unavailable
_embedder = None


def _get_embedder():
    global _embedder
    if _embedder is None:
        try:
            from sentence_transformers import SentenceTransformer

            _embedder = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
            logger.info("LongTermMemory: sentence-transformers loaded for embeddings")
        except Exception:
            _embedder = False
            logger.info("LongTermMemory: sentence-transformers not available, embeddings disabled")
    return _embedder if _embedder is not False else None


def _compute_embedding(text: str) -> bytes | None:
    embedder = _get_embedder()
    if embedder is None:
        return None
    try:
        vector = embedder.encode(text, normalize_embeddings=True)
        import struct

        return struct.pack(f"{len(vector)}f", *vector.tolist())
    except Exception as exc:
        logger.debug("Embedding failed: %s", exc)
        return None


class LongTermMemory:
    """User preferences, learned patterns, and knowledge base.

    All SQLite operations are offloaded to a thread pool to avoid blocking
    the asyncio event loop. A single persistent connection with a threading
    lock ensures thread safety.
    """

    def __init__(self, db_path: str | None = None):
        if db_path is None:
            data_dir = os.environ.get("VIKI_DATA_DIR", "./data")
            Path(data_dir).mkdir(parents=True, exist_ok=True)
            db_path = str(Path(data_dir) / "long_term_memory.db")
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        with self._lock:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS preferences (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at REAL
                );
                CREATE TABLE IF NOT EXISTS learned_patterns (
                    id INTEGER PRIMARY KEY,
                    context TEXT,
                    action TEXT,
                    success INTEGER,
                    embedding BLOB,
                    created_at REAL
                );
                CREATE TABLE IF NOT EXISTS knowledge (
                    id INTEGER PRIMARY KEY,
                    topic TEXT,
                    content TEXT,
                    source TEXT,
                    created_at REAL
                );
                CREATE TABLE IF NOT EXISTS tool_usage (
                    id INTEGER PRIMARY KEY,
                    tool_name TEXT,
                    params TEXT,
                    success INTEGER,
                    duration_ms REAL,
                    created_at REAL
                );
            """
            )
            conn.commit()
        self._conn = conn

    async def set_preference(self, key: str, value: str):
        def _():
            with self._lock:
                self._conn.execute(
                    "INSERT OR REPLACE INTO preferences (key, value, updated_at) VALUES (?, ?, ?)",
                    (key, value, time.time()),
                )
                self._conn.commit()

        await asyncio.to_thread(_)

    async def get_preference(self, key: str) -> str | None:
        def _():
            with self._lock:
                row = self._conn.execute(
                    "SELECT value FROM preferences WHERE key = ?", (key,)
                ).fetchone()
                return row["value"] if row else None

        return await asyncio.to_thread(_)

    async def get_all_preferences(self) -> list[dict]:
        def _():
            with self._lock:
                rows = self._conn.execute(
                    "SELECT key, value, updated_at FROM preferences"
                ).fetchall()
                return [dict(r) for r in rows]

        return await asyncio.to_thread(_)

    async def learn_pattern(self, context: str, action: str, success: bool = True):
        embedding = _compute_embedding(f"{context} {action}")

        def _():
            with self._lock:
                self._conn.execute(
                    "INSERT INTO learned_patterns (context, action, success, embedding, created_at) VALUES (?, ?, ?, ?, ?)",
                    (context, action, 1 if success else 0, embedding, time.time()),
                )
                self._conn.commit()

        await asyncio.to_thread(_)

    async def recall_patterns(self, context: str, limit: int = 5) -> list[dict]:
        def _():
            with self._lock:
                rows = self._conn.execute(
                    "SELECT context, action, success FROM learned_patterns WHERE success = 1 ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [dict(r) for r in rows]

        return await asyncio.to_thread(_)

    async def search_similar_patterns(self, query: str, limit: int = 5) -> list[dict]:
        """Search patterns by semantic similarity using embeddings."""
        query_emb = _compute_embedding(query)
        if query_emb is None:
            return await self.recall_patterns(query, limit=limit)

        import struct

        def _():
            with self._lock:
                rows = self._conn.execute(
                    "SELECT id, context, action, success, embedding, created_at FROM learned_patterns WHERE embedding IS NOT NULL"
                ).fetchall()

            scored = []
            q = list(struct.unpack(f"{len(query_emb) // 4}f", query_emb))
            for r in rows:
                emb_bytes = r["embedding"]
                if not emb_bytes:
                    continue
                try:
                    v = list(struct.unpack(f"{len(emb_bytes) // 4}f", emb_bytes))
                except Exception:
                    continue
                dot = sum(a * b for a, b in zip(q, v, strict=False))
                q_norm = sum(a * a for a in q) ** 0.5
                v_norm = sum(a * a for a in v) ** 0.5
                sim = dot / (q_norm * v_norm) if q_norm and v_norm else 0.0
                scored.append((sim, dict(r)))
                scored.sort(key=lambda x: -x[0])

            return [d for _, d in scored[:limit]]

        return await asyncio.to_thread(_)

    async def store_knowledge(self, topic: str, content: str, source: str = ""):
        def _():
            with self._lock:
                self._conn.execute(
                    "INSERT INTO knowledge (topic, content, source, created_at) VALUES (?, ?, ?, ?)",
                    (topic, content, source, time.time()),
                )
                self._conn.commit()

        await asyncio.to_thread(_)

    async def retrieve_knowledge(self, topic: str, limit: int = 3) -> list[dict]:
        def _():
            with self._lock:
                rows = self._conn.execute(
                    "SELECT topic, content, source, created_at FROM knowledge WHERE topic LIKE ? ORDER BY created_at DESC LIMIT ?",
                    (f"%{topic}%", limit),
                ).fetchall()
                return [dict(r) for r in rows]

        return await asyncio.to_thread(_)

    async def log_tool_usage(self, tool_name: str, params: dict, success: bool, duration_ms: float):
        def _():
            with self._lock:
                self._conn.execute(
                    "INSERT INTO tool_usage (tool_name, params, success, duration_ms, created_at) VALUES (?, ?, ?, ?, ?)",
                    (tool_name, json.dumps(params), 1 if success else 0, duration_ms, time.time()),
                )
                self._conn.commit()

        await asyncio.to_thread(_)

    async def get_tool_stats(self) -> list[dict]:
        def _():
            with self._lock:
                rows = self._conn.execute(
                    """
                    SELECT tool_name,
                           COUNT(*) as total,
                           SUM(CASE WHEN success THEN 1 ELSE 0 END) as successes,
                           AVG(duration_ms) as avg_duration_ms
                    FROM tool_usage
                    GROUP BY tool_name
                    ORDER BY total DESC
                """
                ).fetchall()
                return [dict(r) for r in rows]

        return await asyncio.to_thread(_)

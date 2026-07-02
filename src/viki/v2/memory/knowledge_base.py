"""KnowledgeBase — vector-backed persistent knowledge with embedding similarity search."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import struct
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

logger = logging.getLogger(__name__)

_embedder = None
_embedder_lock = threading.Lock()


def _get_embedder():
    global _embedder
    if _embedder is not None:
        return _embedder if _embedder is not False else None
    with _embedder_lock:
        if _embedder is not None:
            return _embedder if _embedder is not False else None
        try:
            from sentence_transformers import SentenceTransformer

            _embedder = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
            logger.info("KnowledgeBase: sentence-transformers loaded")
        except Exception:
            _embedder = False
            logger.info("KnowledgeBase: sentence-transformers unavailable, embedding disabled")
    return _embedder if _embedder is not False else None


def _compute_embedding(text: str) -> bytes | None:
    embedder = _get_embedder()
    if embedder is None:
        return None
    try:
        vector = embedder.encode(text, normalize_embeddings=True)
        return struct.pack(f"{len(vector)}f", *vector.tolist())
    except Exception as exc:
        logger.debug("KnowledgeBase embedding failed: %s", exc)
        return None


def _cosine_similarity(a: bytes, b: bytes) -> float:
    fa = struct.unpack(f"{len(a) // 4}f", a)
    fb = struct.unpack(f"{len(b) // 4}f", b)
    dot = sum(x * y for x, y in zip(fa, fb, strict=False))
    return cast("float", dot)


@dataclass
class KnowledgeEntry:
    id: int = 0
    key: str = ""
    content: str = ""
    source: str = ""
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: bytes | None = None
    created_at: float = 0.0
    updated_at: float = 0.0
    access_count: int = 0


class KnowledgeBase:
    def __init__(self, db_path: str | None = None):
        if db_path is None:
            db_path = os.environ.get(
                "VIKI_KNOWLEDGE_DB",
                str(Path.home() / ".viki" / "knowledge.db"),
            )
        self._db_path = db_path
        os.makedirs(os.path.dirname(self._db_path) or ".", exist_ok=True)
        self._local = threading.local()
        self._ensure_schema()

    @property
    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return cast(sqlite3.Connection, self._local.conn)

    def _ensure_schema(self):
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS knowledge (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                key         TEXT UNIQUE NOT NULL,
                content     TEXT NOT NULL,
                source      TEXT DEFAULT '',
                tags        TEXT DEFAULT '[]',
                metadata    TEXT DEFAULT '{}',
                embedding   BLOB,
                created_at  REAL NOT NULL,
                updated_at  REAL NOT NULL,
                access_count INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_knowledge_key ON knowledge(key);
            CREATE INDEX IF NOT EXISTS idx_knowledge_tags ON knowledge(tags);
        """
        )

    def store(
        self,
        key: str,
        content: str,
        source: str = "",
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        now = time.time()
        embedding = _compute_embedding(content)
        tags_json = json.dumps(tags or [])
        meta_json = json.dumps(metadata or {})
        try:
            self._conn.execute(
                """INSERT OR REPLACE INTO knowledge
                   (key, content, source, tags, metadata, embedding, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (key, content, source, tags_json, meta_json, embedding, now, now),
            )
            self._conn.commit()
            return True
        except Exception as exc:
            logger.error("KnowledgeBase.store(%s) failed: %s", key, exc)
            return False

    def store_async(
        self,
        key: str,
        content: str,
        source: str = "",
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        threading.Thread(
            target=self.store,
            args=(key, content, source, tags, metadata),
            daemon=True,
        ).start()

    def get(self, key: str) -> KnowledgeEntry | None:
        row = self._conn.execute("SELECT * FROM knowledge WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        self._conn.execute(
            "UPDATE knowledge SET access_count = access_count + 1 WHERE id = ?", (row["id"],)
        )
        self._conn.commit()
        return self._row_to_entry(row)

    def delete(self, key: str) -> bool:
        cursor = self._conn.execute("DELETE FROM knowledge WHERE key = ?", (key,))
        self._conn.commit()
        return cursor.rowcount > 0

    def list_keys(self, tag: str | None = None) -> list[str]:
        if tag:
            rows = self._conn.execute(
                "SELECT key FROM knowledge WHERE tags LIKE ? ORDER BY updated_at DESC",
                (f"%{tag}%",),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT key FROM knowledge ORDER BY updated_at DESC"
            ).fetchall()
        return [r["key"] for r in rows]

    def search_similar(
        self, query: str, top_k: int = 5, min_score: float = 0.3
    ) -> list[tuple[KnowledgeEntry, float]]:
        query_emb = _compute_embedding(query)
        if query_emb is None:
            rows = self._conn.execute(
                "SELECT * FROM knowledge ORDER BY access_count DESC LIMIT ?", (top_k,)
            ).fetchall()
            return [(self._row_to_entry(r), 0.0) for r in rows]

        all_rows = self._conn.execute(
            "SELECT * FROM knowledge WHERE embedding IS NOT NULL"
        ).fetchall()
        scored: list[tuple] = []
        for row in all_rows:
            stored_emb = row["embedding"]
            if stored_emb is None or len(stored_emb) != len(query_emb):
                continue
            score = _cosine_similarity(query_emb, stored_emb)
            if score >= min_score:
                scored.append((score, row))
        scored.sort(key=lambda x: -x[0])
        results = []
        for score, row in scored[:top_k]:
            entry = self._row_to_entry(row)
            results.append((entry, score))
        return results

    def get_stats(self) -> dict[str, Any]:
        row = self._conn.execute(
            "SELECT COUNT(*) as count, SUM(access_count) as total_access FROM knowledge"
        ).fetchone()
        return {
            "total_entries": row["count"] or 0,
            "total_accesses": row["total_access"] or 0,
            "db_path": self._db_path,
        }

    def _row_to_entry(self, row: sqlite3.Row) -> KnowledgeEntry:
        return KnowledgeEntry(
            id=row["id"],
            key=row["key"],
            content=row["content"],
            source=row["source"] or "",
            tags=json.loads(row["tags"] or "[]"),
            metadata=json.loads(row["metadata"] or "{}"),
            embedding=row["embedding"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            access_count=row["access_count"] or 0,
        )

    def close(self):
        if hasattr(self._local, "conn") and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None

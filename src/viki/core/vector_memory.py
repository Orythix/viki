"""
Vector memory backends (Phase 6).

Replaces the O(N) linear scan in `LearningModule.get_relevant_lessons` with
either:

    1. sqlite-vss (preferred, on-disk, scales to millions of rows), or
    2. an in-memory numpy index (works anywhere with numpy installed), or
    3. a final pure-Python lexical fallback (always available).

The interface is intentionally tiny so we can swap backends without leaking
implementation detail into the LearningModule:

    backend = build_vector_backend(dim=384, db_path="./data/vector.sqlite")
    backend.upsert(id=42, embedding=[...], text="...")
    hits = backend.search(query_embedding, top_k=5)

Each backend versions its own state so a process restart resumes from disk
where possible.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from viki.config.logger import viki_logger


@dataclass
class VectorHit:
    id: Any
    text: str
    score: float
    metadata: dict[str, Any]


class _BaseVectorBackend:
    """Common interface every backend obeys."""

    backend_name: str = "abstract"

    def upsert(
        self, id: Any, embedding: list[float], text: str, metadata: dict[str, Any] | None = None
    ) -> None:
        raise NotImplementedError

    def upsert_many(self, rows: Iterable[tuple[Any, list[float], str, dict[str, Any]]]) -> int:
        n = 0
        for _id, emb, txt, meta in rows:
            self.upsert(_id, emb, txt, meta)
            n += 1
        return n

    def delete(self, id: Any) -> None:
        raise NotImplementedError

    def search(
        self,
        query: list[float],
        top_k: int = 5,
        query_text: str | None = None,
    ) -> list[VectorHit]:
        raise NotImplementedError

    def stats(self) -> dict[str, Any]:
        return {"backend": self.backend_name}


class _SqliteVssBackend(_BaseVectorBackend):
    """sqlite-vss-backed vector index. Persistent, O(log N) approximate."""

    backend_name = "sqlite-vss"

    def __init__(self, db_path: str, dim: int):
        try:
            import sqlite_vss
        except Exception as e:
            raise RuntimeError(f"sqlite-vss not installed: {e}")
        self._sqlite_vss = sqlite_vss
        self.db_path = db_path
        self.dim = dim
        os.makedirs(os.path.dirname(os.path.abspath(db_path)) or ".", exist_ok=True)
        self.conn = sqlite3.connect(db_path, timeout=30.0)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.row_factory = sqlite3.Row
        self.conn.enable_load_extension(True)
        sqlite_vss.load(self.conn)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self.conn.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS vmem (
                id INTEGER PRIMARY KEY,
                text TEXT NOT NULL,
                metadata TEXT,
                created_at REAL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS vmem_vss USING vss0(
                embedding({self.dim})
            );
            """
        )
        self.conn.commit()

    def upsert(self, id, embedding, text, metadata=None):
        meta_json = json.dumps(metadata or {})
        cur = self.conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO vmem (id, text, metadata, created_at) VALUES (?, ?, ?, ?)",
            (int(id), text, meta_json, time.time()),
        )
        cur.execute("DELETE FROM vmem_vss WHERE rowid = ?", (int(id),))
        cur.execute(
            "INSERT INTO vmem_vss(rowid, embedding) VALUES (?, ?)",
            (int(id), json.dumps(list(embedding))),
        )
        self.conn.commit()

    def delete(self, id):
        cur = self.conn.cursor()
        cur.execute("DELETE FROM vmem WHERE id = ?", (int(id),))
        cur.execute("DELETE FROM vmem_vss WHERE rowid = ?", (int(id),))
        self.conn.commit()

    def search(self, query, top_k=5, query_text=None):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT rowid, distance FROM vmem_vss WHERE vss_search(embedding, ?) LIMIT ?",
            (json.dumps(list(query)), int(top_k)),
        )
        rows = cur.fetchall()
        if not rows:
            return []
        ids = [r["rowid"] for r in rows]
        placeholders = ",".join(["?"] * len(ids))
        meta_rows = {
            r["id"]: r
            for r in cur.execute(
                f"SELECT id, text, metadata FROM vmem WHERE id IN ({placeholders})", ids
            ).fetchall()
        }
        out: list[VectorHit] = []
        for r in rows:
            meta_row = meta_rows.get(r["rowid"])
            if not meta_row:
                continue
            try:
                meta = json.loads(meta_row["metadata"] or "{}")
            except Exception:
                meta = {}
            # sqlite-vss returns L2 distance; convert to similarity-ish score.
            distance = float(r["distance"])
            score = 1.0 / (1.0 + distance)
            out.append(
                VectorHit(id=meta_row["id"], text=meta_row["text"], score=score, metadata=meta)
            )
        return out

    def stats(self):
        n = self.conn.execute("SELECT COUNT(*) FROM vmem").fetchone()[0]
        return {"backend": self.backend_name, "count": n, "dim": self.dim}


class _NumpyMemoryBackend(_BaseVectorBackend):
    """In-memory numpy index. O(N) per query but with a tight inner loop and
    no Python overhead for dot products. Persists to a single JSON snapshot."""

    backend_name = "numpy-memory"

    def __init__(self, dim: int, snapshot_path: str | None = None):
        try:
            import numpy as np
        except Exception as e:
            raise RuntimeError(f"numpy not installed: {e}")
        self.np = np
        self.dim = dim
        self.snapshot_path = snapshot_path
        self._ids: list[Any] = []
        self._texts: list[str] = []
        self._metas: list[dict[str, Any]] = []
        self._matrix: Any = None
        self._load_snapshot()

    def _load_snapshot(self) -> None:
        if not self.snapshot_path or not os.path.isfile(self.snapshot_path):
            return
        try:
            with open(self.snapshot_path, encoding="utf-8") as f:
                data = json.load(f)
            embs = data.get("embeddings", [])
            if embs:
                self._ids = data.get("ids", [])
                self._texts = data.get("texts", [])
                self._metas = data.get("metadata", [])
                self._matrix = self.np.asarray(embs, dtype=self.np.float32)
        except Exception as e:
            viki_logger.debug("NumpyMemoryBackend: snapshot load failed: %s", e)

    def _save_snapshot(self) -> None:
        if not self.snapshot_path:
            return
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.snapshot_path)) or ".", exist_ok=True)
            data = {
                "ids": list(self._ids),
                "texts": list(self._texts),
                "metadata": list(self._metas),
                "embeddings": self._matrix.tolist() if self._matrix is not None else [],
            }
            with open(self.snapshot_path, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception as e:
            viki_logger.debug("NumpyMemoryBackend: snapshot save failed: %s", e)

    def upsert(self, id, embedding, text, metadata=None):
        emb = self.np.asarray(embedding, dtype=self.np.float32)
        if emb.shape[0] != self.dim:
            raise ValueError(f"embedding dim {emb.shape[0]} != configured {self.dim}")
        if id in self._ids:
            idx = self._ids.index(id)
            self._matrix[idx] = emb
            self._texts[idx] = text
            self._metas[idx] = metadata or {}
        else:
            self._ids.append(id)
            self._texts.append(text)
            self._metas.append(metadata or {})
            if self._matrix is None:
                self._matrix = emb.reshape(1, -1)
            else:
                self._matrix = self.np.vstack([self._matrix, emb.reshape(1, -1)])
        self._save_snapshot()

    def upsert_many(self, rows) -> int:
        """Batched upsert: one matrix stack and one snapshot write for the whole
        batch, instead of the base class's per-row loop (which here would mean
        an O(n^2) vstack/list-scan and a full JSON snapshot rewrite per row —
        catastrophic once the lesson count reaches the thousands)."""
        rows = list(rows)
        if not rows:
            return 0
        id_to_idx = {id_: i for i, id_ in enumerate(self._ids)}
        new_ids: list[Any] = []
        new_texts: list[str] = []
        new_metas: list[dict[str, Any]] = []
        new_embs: list[Any] = []
        n = 0
        for _id, emb, txt, meta in rows:
            emb_arr = self.np.asarray(emb, dtype=self.np.float32)
            if emb_arr.shape[0] != self.dim:
                continue
            idx = id_to_idx.get(_id)
            if idx is not None:
                self._matrix[idx] = emb_arr
                self._texts[idx] = txt
                self._metas[idx] = meta or {}
            else:
                id_to_idx[_id] = len(self._ids) + len(new_ids)
                new_ids.append(_id)
                new_texts.append(txt)
                new_metas.append(meta or {})
                new_embs.append(emb_arr)
            n += 1
        if new_embs:
            stacked = self.np.vstack(new_embs)
            self._matrix = (
                stacked if self._matrix is None else self.np.vstack([self._matrix, stacked])
            )
            self._ids.extend(new_ids)
            self._texts.extend(new_texts)
            self._metas.extend(new_metas)
        self._save_snapshot()
        return n

    def delete(self, id):
        if id not in self._ids:
            return
        idx = self._ids.index(id)
        self._ids.pop(idx)
        self._texts.pop(idx)
        self._metas.pop(idx)
        self._matrix = self.np.delete(self._matrix, idx, axis=0)
        self._save_snapshot()

    def search(self, query, top_k=5, query_text=None):
        if self._matrix is None or len(self._ids) == 0:
            return []
        q = self.np.asarray(query, dtype=self.np.float32)
        # Cosine similarity.
        denom = (self.np.linalg.norm(self._matrix, axis=1) * self.np.linalg.norm(q)) + 1e-12
        sims = (self._matrix @ q) / denom
        top = self.np.argsort(-sims)[: int(top_k)]
        return [
            VectorHit(
                id=self._ids[int(i)],
                text=self._texts[int(i)],
                score=float(sims[int(i)]),
                metadata=self._metas[int(i)],
            )
            for i in top
        ]

    def stats(self):
        return {
            "backend": self.backend_name,
            "count": len(self._ids),
            "dim": self.dim,
        }


_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "with",
    "i",
    "you",
    "we",
    "they",
    "this",
    "these",
    "those",
    "what",
    "how",
    "why",
    "do",
    "does",
    "did",
    "but",
    "if",
    "then",
    "so",
    "not",
    "no",
}


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    out: list[str] = []
    word = []
    for ch in text.lower():
        if ch.isalnum() or ch == "_":
            word.append(ch)
        else:
            if word:
                token = "".join(word)
                if len(token) > 1 and token not in _STOPWORDS:
                    out.append(token)
                word = []
    if word:
        token = "".join(word)
        if len(token) > 1 and token not in _STOPWORDS:
            out.append(token)
    return out


class _LexicalFallbackBackend(_BaseVectorBackend):
    """Pure-python token overlap fallback when neither numpy nor sqlite-vss is
    available. Embeddings are ignored; ranking uses Jaccard token overlap on
    text only. Callers must pass `query_text=...` for ranking to be meaningful;
    otherwise we return an empty result and let the caller's own lexical path
    kick in (rather than returning recency-biased noise as before)."""

    backend_name = "lexical-fallback"

    def __init__(self):
        self._texts: dict[Any, str] = {}
        self._metas: dict[Any, dict[str, Any]] = {}
        self._token_cache: dict[Any, set] = {}

    def upsert(self, id, embedding, text, metadata=None):
        self._texts[id] = text
        self._metas[id] = metadata or {}
        self._token_cache[id] = set(_tokenize(text))

    def delete(self, id):
        self._texts.pop(id, None)
        self._metas.pop(id, None)
        self._token_cache.pop(id, None)

    def search(self, query, top_k=5, query_text=None):
        # P0 fix: real token-overlap ranking. The previous implementation
        # returned `list(self._texts.items())[-top_k:]` (recency bias) which
        # made retrieval semantically meaningless. Now:
        #   - query_text → score by Jaccard token overlap, return top_k.
        #   - no query_text → return [] so the caller can apply its own ranker
        #     instead of receiving noise.
        if not query_text:
            return []
        q_tokens = set(_tokenize(query_text))
        if not q_tokens:
            return []
        scored: list[tuple[float, Any, str]] = []
        for _id, tokens in self._token_cache.items():
            if not tokens:
                continue
            inter = q_tokens & tokens
            if not inter:
                continue
            union = q_tokens | tokens
            score = len(inter) / max(1, len(union))
            scored.append((score, _id, self._texts.get(_id, "")))
        scored.sort(key=lambda r: -r[0])
        scored = scored[: int(top_k)]
        return [
            VectorHit(id=_id, text=text, score=float(score), metadata=self._metas.get(_id, {}))
            for score, _id, text in scored
        ]

    def stats(self):
        return {"backend": self.backend_name, "count": len(self._texts)}


def build_vector_backend(
    dim: int,
    db_path: str | None = None,
    prefer: list[str] | None = None,
) -> _BaseVectorBackend:
    """
    Pick the best available backend in priority order. Returns the lexical
    fallback only when no vector library is available.
    """
    order = prefer or ["sqlite-vss", "numpy-memory", "lexical-fallback"]
    for choice in order:
        try:
            if choice == "sqlite-vss" and db_path:
                return _SqliteVssBackend(db_path=db_path, dim=dim)
            if choice == "numpy-memory":
                snap = None
                if db_path:
                    snap = os.path.splitext(db_path)[0] + "_numpy.json"
                return _NumpyMemoryBackend(dim=dim, snapshot_path=snap)
            if choice == "lexical-fallback":
                return _LexicalFallbackBackend()
        except Exception as e:
            viki_logger.debug("VectorMemory: %s unavailable: %s", choice, e)
    return _LexicalFallbackBackend()

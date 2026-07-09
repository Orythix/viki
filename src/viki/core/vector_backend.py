"""
Pluggable vector backend interface.

Provides a common interface for vector stores with SQLite (sqlite-vss) as the
default and optional adapters for Qdrant and Chroma for 100k+ lesson libraries.
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, cast

from viki.config.logger import viki_logger

try:
    import numpy as np

    _HAS_NP = True
except ImportError:
    _HAS_NP = False


@dataclass
class VectorHit:
    """A single search result from a vector backend."""

    id: int
    vector: list[float]
    text: str = ""
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorBackend(ABC):
    """Abstract interface for vector similarity search."""

    @abstractmethod
    def upsert(
        self, id: int, vector: list[float], text: str = "", metadata: dict[str, Any] | None = None
    ) -> None:
        """Insert or update a single vector."""

    @abstractmethod
    def upsert_many(self, rows: list[tuple[int, list[float], str, dict[str, Any] | None]]) -> None:
        """Bulk upsert vectors."""

    @abstractmethod
    def search(self, query: list[float], top_k: int = 10, query_text: str = "") -> list[VectorHit]:
        """Search for nearest neighbors."""

    @abstractmethod
    def count(self) -> int:
        """Return the number of vectors stored."""

    @abstractmethod
    def clear(self) -> None:
        """Remove all vectors."""


class NumpyMemoryBackend(VectorBackend):
    """
    In-memory numpy-based vector backend.

    Best for < 50k vectors.  All data is lost on process restart.
    """

    def __init__(self, dim: int):
        self._dim = dim
        self._ids: list[int] = []
        self._vectors: list[list[float]] = []
        self._texts: list[str] = []
        self._metadatas: list[dict[str, Any]] = []

    def upsert(
        self, id: int, vector: list[float], text: str = "", metadata: dict[str, Any] | None = None
    ) -> None:
        try:
            idx = self._ids.index(id)
            self._vectors[idx] = vector
            self._texts[idx] = text
            if metadata:
                self._metadatas[idx] = metadata
        except ValueError:
            self._ids.append(id)
            self._vectors.append(vector)
            self._texts.append(text)
            self._metadatas.append(metadata or {})

    def upsert_many(self, rows: list[tuple[int, list[float], str, dict[str, Any] | None]]) -> None:
        for id, vec, text, meta in rows:
            self.upsert(id, vec, text, meta)

    def search(self, query: list[float], top_k: int = 10, query_text: str = "") -> list[VectorHit]:
        if not self._vectors or not _HAS_NP:
            return []
        arr = np.array(self._vectors, dtype=np.float32)
        q = np.array(query, dtype=np.float32)
        # Cosine similarity
        norms = np.linalg.norm(arr, axis=1)
        q_norm = np.linalg.norm(q)
        if q_norm == 0:
            return []
        similarities = np.dot(arr, q) / (norms * q_norm + 1e-10)
        top_indices = np.argsort(similarities)[-top_k:][::-1]
        return [
            VectorHit(
                id=self._ids[i],
                vector=self._vectors[i],
                text=self._texts[i],
                score=float(similarities[i]),
                metadata=self._metadatas[i],
            )
            for i in top_indices
        ]

    def count(self) -> int:
        return len(self._ids)

    def clear(self) -> None:
        self._ids.clear()
        self._vectors.clear()
        self._texts.clear()
        self._metadatas.clear()


class SQLiteVssBackend(VectorBackend):
    """
    SQLite-based vector backend using sqlite-vss extension.

    Requires: pip install sqlite-vss
    Persistent across restarts, good for up to ~100k vectors.
    """

    def __init__(self, dim: int, db_path: str):
        self._dim = dim
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _init_db(self) -> None:
        try:
            import sqlite_vss  # noqa: F401
        except ImportError:
            viki_logger.warning("sqlite-vss not installed; falling back to numpy backend")
            raise

        import sqlite3

        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS vss_vectors USING vss0(v({self._dim}))"
        )
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS vss_meta (
                id INTEGER PRIMARY KEY,
                text TEXT,
                metadata TEXT
            )"""
        )

    def upsert(
        self, id: int, vector: list[float], text: str = "", metadata: dict[str, Any] | None = None
    ) -> None:
        if self._conn is None:
            return
        import json as _json

        self._conn.execute(
            "INSERT OR REPLACE INTO vss_vectors (id, v) VALUES (?, ?)",
            (id, _json.dumps(vector)),
        )
        self._conn.execute(
            "INSERT OR REPLACE INTO vss_meta (id, text, metadata) VALUES (?, ?, ?)",
            (id, text, _json.dumps(metadata or {})),
        )
        self._conn.commit()

    def upsert_many(self, rows: list[tuple[int, list[float], str, dict[str, Any] | None]]) -> None:
        if self._conn is None:
            return
        import json as _json

        cur = self._conn.cursor()
        for id, vec, text, meta in rows:
            cur.execute(
                "INSERT OR REPLACE INTO vss_vectors (id, v) VALUES (?, ?)",
                (id, _json.dumps(vec)),
            )
            cur.execute(
                "INSERT OR REPLACE INTO vss_meta (id, text, metadata) VALUES (?, ?, ?)",
                (id, text, _json.dumps(meta or {})),
            )
        self._conn.commit()

    def search(self, query: list[float], top_k: int = 10, query_text: str = "") -> list[VectorHit]:
        if self._conn is None:
            return []
        import json as _json

        cur = self._conn.cursor()
        cur.execute(
            "SELECT v.id, distance, vss_meta.text, vss_meta.metadata FROM vss_vectors v "
            "LEFT JOIN vss_meta ON v.id = vss_meta.id "
            "WHERE vss_search(v.v, ?) "
            "ORDER BY distance LIMIT ?",
            (_json.dumps(query), top_k),
        )
        results: list[VectorHit] = []
        for row in cur.fetchall():
            results.append(
                VectorHit(
                    id=row[0],
                    vector=[],
                    text=row[2] or "",
                    score=1.0 - float(row[1]),
                    metadata=_json.loads(row[3]) if row[3] else {},
                )
            )
        return results

    def count(self) -> int:
        if self._conn is None:
            return 0
        cur = self._conn.cursor()
        cur.execute("SELECT COUNT(*) FROM vss_vectors")
        return int(cur.fetchone()[0])

    def clear(self) -> None:
        if self._conn is None:
            return
        self._conn.execute("DELETE FROM vss_vectors")
        self._conn.execute("DELETE FROM vss_meta")
        self._conn.commit()


class QdrantBackend(VectorBackend):
    """
    Qdrant-based vector backend.

    Runs in-memory by default.  Pass ``db_path`` for on-disk persistence::

        QdrantBackend(dim=384, db_path="./data/qdrant_db")
    """

    def __init__(self, dim: int, db_path: str = "", collection_name: str = "viki_vectors"):
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http.models import Distance, VectorParams
        except ImportError:
            raise RuntimeError(
                "qdrant-client not installed.  Run: pip install qdrant-client"
            ) from None

        self._dim = dim
        self._collection = collection_name
        self._client = QdrantClient(path=db_path) if db_path else QdrantClient(":memory:")
        self._client.recreate_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )

    def _encode_payload(self, text: str, metadata: dict[str, Any] | None) -> dict[str, Any]:
        payload: dict[str, Any] = {"text": text or ""}
        if metadata:
            payload["metadata"] = metadata
        return payload

    def upsert(
        self, id: int, vector: list[float], text: str = "", metadata: dict[str, Any] | None = None
    ) -> None:
        from qdrant_client.http.models import PointStruct

        self._client.upsert(
            collection_name=self._collection,
            points=[
                PointStruct(
                    id=id,
                    vector=vector,
                    payload=self._encode_payload(text, metadata),
                )
            ],
        )

    def upsert_many(self, rows: list[tuple[int, list[float], str, dict[str, Any] | None]]) -> None:
        from qdrant_client.http.models import PointStruct

        self._client.upsert(
            collection_name=self._collection,
            points=[
                PointStruct(
                    id=row[0],
                    vector=row[1],
                    payload=self._encode_payload(row[2], row[3]),
                )
                for row in rows
            ],
        )

    def search(self, query: list[float], top_k: int = 10, query_text: str = "") -> list[VectorHit]:
        results = self._client.search(
            collection_name=self._collection,
            query_vector=query,
            limit=top_k,
        )
        hits: list[VectorHit] = []
        for r in results:
            text = (r.payload or {}).get("text", "")
            meta = (r.payload or {}).get("metadata", {})
            hits.append(
                VectorHit(
                    id=int(r.id),
                    vector=[],
                    text=str(text) if text else "",
                    score=float(r.score),
                    metadata=dict(meta) if isinstance(meta, dict) else {},
                )
            )
        return hits

    def count(self) -> int:
        info = self._client.get_collection(collection_name=self._collection)
        return cast(int, info.points_count)

    def clear(self) -> None:
        self._client.delete_collection(collection_name=self._collection)


class ChromaBackend(VectorBackend):
    """
    Chroma-based vector backend.

    Runs in-memory by default.  Pass ``db_path`` for on-disk persistence::

        ChromaBackend(dim=384, db_path="./data/chroma_db")
    """

    def __init__(self, dim: int, db_path: str = "", collection_name: str = "viki_vectors"):
        try:
            import chromadb
        except ImportError:
            raise RuntimeError("chromadb not installed.  Run: pip install chromadb") from None

        self._dim = dim
        self._collection_name = collection_name
        settings = (
            chromadb.config.Settings(
                is_persistent=True,
                persist_directory=db_path,
                anonymized_telemetry=False,
            )
            if db_path
            else chromadb.config.Settings(anonymized_telemetry=False)
        )
        self._client = chromadb.Client(settings) if db_path else chromadb.Client(settings)
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert(
        self, id: int, vector: list[float], text: str = "", metadata: dict[str, Any] | None = None
    ) -> None:
        self._collection.upsert(
            ids=[str(id)],
            embeddings=[vector],
            metadatas=[{**(metadata or {}), "text": text}],
        )

    def upsert_many(self, rows: list[tuple[int, list[float], str, dict[str, Any] | None]]) -> None:
        ids = [str(r[0]) for r in rows]
        embeddings = [r[1] for r in rows]
        metadatas = [{**(r[3] or {}), "text": r[2]} for r in rows]
        self._collection.upsert(ids=ids, embeddings=embeddings, metadatas=metadatas)

    def search(self, query: list[float], top_k: int = 10, query_text: str = "") -> list[VectorHit]:
        results = self._collection.query(query_embeddings=[query], n_results=top_k)
        hits: list[VectorHit] = []
        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        for i, raw_id in enumerate(ids):
            meta = metadatas[i] if i < len(metadatas) else {}
            text = (meta or {}).get("text", "")
            dist = distances[i] if i < len(distances) else 1.0
            hits.append(
                VectorHit(
                    id=int(raw_id) if raw_id else 0,
                    vector=[],
                    text=str(text) if text else "",
                    score=max(0.0, 1.0 - float(dist)),
                    metadata={k: v for k, v in (meta or {}).items() if k != "text"},
                )
            )
        return hits

    def count(self) -> int:
        return cast(int, self._collection.count())

    def clear(self) -> None:
        self._client.delete_collection(name=self._collection_name)


def build_vector_backend(
    dim: int,
    db_path: str = "",
    prefer: list[str] | None = None,
) -> VectorBackend:
    """
    Build the best available vector backend.

    ``prefer`` is an ordered list of backend names to try first:
    ``["sqlite-vss", "qdrant", "chroma", "numpy-memory"]``.
    Falls back to the next available backend if the preferred one fails.
    """
    prefer = prefer or ["sqlite-vss", "numpy-memory"]

    for name in prefer:
        try:
            if name == "sqlite-vss" and db_path:
                return SQLiteVssBackend(dim, db_path)
            elif name == "qdrant":
                return QdrantBackend(dim, db_path=db_path)
            elif name == "chroma":
                return ChromaBackend(dim, db_path=db_path)
            elif name == "numpy-memory":
                return NumpyMemoryBackend(dim)
        except Exception as e:
            viki_logger.debug("Vector backend '%s' unavailable: %s", name, e)
            continue

    # Final fallback
    return NumpyMemoryBackend(dim)

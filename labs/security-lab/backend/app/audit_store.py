"""
Audit persistence for security events, tool runs, and LLM metadata.

Supports SQLite (default) and PostgreSQL via the same schema for local labs
that outgrow a single file.

Risks
-----
- Weak DB credentials or exposed ports leak full audit history.
- SQLite file permissions must restrict read/write to the lab service account.

Mitigations
-----------
- Run containers as non-root; bind to 127.0.0.1; use strong ``LAB_API_KEY``.
- For PostgreSQL: dedicated role, minimal grants, TLS to DB in shared networks.
- Encrypt backups if they leave the lab machine.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


@dataclass
class AuditEntry:
    id: str
    ts: float
    kind: str
    payload: dict[str, Any]


def _is_postgres_url(url: str) -> bool:
    u = url.strip().lower()
    return u.startswith(("postgresql://", "postgres://"))


def _sqlite_file_path(database_url: str) -> Path:
    """Resolve filesystem path from sqlalchemy-style sqlite URL."""
    parsed = urlparse(database_url)
    if parsed.scheme != "sqlite":
        raise ValueError(f"expected sqlite URL, got {parsed.scheme!r}")
    path = parsed.path or ""
    if path.startswith("//"):
        path = path[1:]
    # urllib may yield '/C:/...' on Windows — pathlib rejects the leading slash.
    if re.match(r"^/[A-Za-z]:/", path):
        path = path[1:]
    if not path:
        raise ValueError("sqlite URL missing path")
    return Path(path)


class AuditStore:
    def __init__(self, database_url: str) -> None:
        self._url = database_url.strip()
        self._lock = threading.Lock()
        if _is_postgres_url(self._url):
            self._backend = "postgres"
            self._init_postgres_schema()
        else:
            self._backend = "sqlite"
            self._path = _sqlite_file_path(self._url)
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._init_sqlite_schema()

    def _init_sqlite_schema(self) -> None:
        with self._connect_sqlite() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id TEXT PRIMARY KEY,
                    ts REAL NOT NULL,
                    kind TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_kind ON audit_log(kind)")
            conn.commit()

    def _init_postgres_schema(self) -> None:
        import psycopg

        with psycopg.connect(self._url) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id TEXT PRIMARY KEY,
                    ts DOUBLE PRECISION NOT NULL,
                    kind TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_kind ON audit_log(kind)")
            conn.commit()

    @contextmanager
    def _connect_sqlite(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self._path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def append(self, kind: str, payload: dict[str, Any]) -> str:
        eid = str(uuid.uuid4())
        ts = time.time()
        blob = json.dumps(payload, ensure_ascii=False)
        with self._lock:
            if self._backend == "sqlite":
                with self._connect_sqlite() as conn:
                    conn.execute(
                        "INSERT INTO audit_log (id, ts, kind, payload) VALUES (?, ?, ?, ?)",
                        (eid, ts, kind, blob),
                    )
                    conn.commit()
            else:
                import psycopg

                with psycopg.connect(self._url) as conn:
                    conn.execute(
                        "INSERT INTO audit_log (id, ts, kind, payload) VALUES (%s, %s, %s, %s)",
                        (eid, ts, kind, blob),
                    )
                    conn.commit()
        return eid

    def recent(self, limit: int = 100, kind: str | None = None) -> list[AuditEntry]:
        with self._lock:
            if self._backend == "sqlite":
                q = "SELECT id, ts, kind, payload FROM audit_log"
                args: list[Any] = []
                if kind:
                    q += " WHERE kind = ?"
                    args.append(kind)
                q += " ORDER BY ts DESC LIMIT ?"
                args.append(limit)
                with self._connect_sqlite() as conn:
                    rows = conn.execute(q, args).fetchall()
            else:
                import psycopg
                from psycopg.rows import dict_row

                q = "SELECT id, ts, kind, payload FROM audit_log"
                args_pg: list[Any] = []
                if kind:
                    q += " WHERE kind = %s"
                    args_pg.append(kind)
                q += " ORDER BY ts DESC LIMIT %s"
                args_pg.append(limit)
                with psycopg.connect(self._url, row_factory=dict_row) as conn:
                    rows = conn.execute(q, args_pg).fetchall()

        out: list[AuditEntry] = []
        for r in rows:
            out.append(
                AuditEntry(
                    id=str(r["id"]),
                    ts=float(r["ts"]),
                    kind=str(r["kind"]),
                    payload=json.loads(str(r["payload"])),
                )
            )
        return out

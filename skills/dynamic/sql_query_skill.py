"""
SQL query skill (dynamic / Phase 4).

Executes read-only SELECT queries against SQLite (default), Postgres, or MySQL.
Designed as a safe, non-destructive starting point. Write queries (INSERT,
UPDATE, DELETE, DDL) are explicitly rejected so this skill stays in the
"safe_utilities" capability tier.

P2 upgrade: pagination via `limit` + `offset` (returns `next_offset`) and
multi-engine dispatch via `engine` ("sqlite" | "postgres" | "mysql") with
optional connection params (`dsn`, `host`, `port`, `user`, `password`, `db`).
External engines degrade gracefully if `psycopg`/`pymysql` aren't installed.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from typing import Any, Dict, List, Tuple

from skills.base import BaseSkill

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|attach|detach|pragma|replace|grant|revoke)\b",
    re.IGNORECASE,
)


def _validate_select(query: str) -> str:
    if not query.lower().lstrip().startswith("select"):
        return "Error: only SELECT queries are allowed."
    if _FORBIDDEN.search(query):
        return "Error: query contains forbidden write/DDL keyword."
    return ""


def _run_sqlite(db_path: str, query: str, limit: int, offset: int) -> Tuple[List[Dict[str, Any]], int]:
    if not db_path or not os.path.isfile(db_path):
        raise FileNotFoundError(f"sqlite db not found: {db_path}")
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10.0) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(f"{query} LIMIT {limit} OFFSET {offset}")
        rows = [dict(r) for r in cur.fetchall()]
    return rows, len(rows)


def _run_postgres(params: Dict[str, Any], query: str, limit: int, offset: int) -> Tuple[List[Dict[str, Any]], int]:
    try:
        import psycopg  # type: ignore
        from psycopg.rows import dict_row  # type: ignore
    except Exception as e:
        raise RuntimeError(f"postgres engine requires `psycopg` (pip install psycopg[binary]): {e}")
    conninfo = params.get("dsn") or _build_pg_conninfo(params)
    with psycopg.connect(conninfo, autocommit=True) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"{query} LIMIT %s OFFSET %s", (limit, offset))
            rows = list(cur.fetchall())
    return rows, len(rows)


def _build_pg_conninfo(params: Dict[str, Any]) -> str:
    parts = []
    for k, key in (("host", "host"), ("port", "port"), ("user", "user"),
                   ("password", "password"), ("db", "dbname")):
        v = params.get(k)
        if v is not None and v != "":
            parts.append(f"{key}={v}")
    return " ".join(parts)


def _run_mysql(params: Dict[str, Any], query: str, limit: int, offset: int) -> Tuple[List[Dict[str, Any]], int]:
    try:
        import pymysql  # type: ignore
        import pymysql.cursors  # type: ignore
    except Exception as e:
        raise RuntimeError(f"mysql engine requires `pymysql` (pip install pymysql): {e}")
    conn = pymysql.connect(
        host=params.get("host", "localhost"),
        port=int(params.get("port", 3306)),
        user=params.get("user", "root"),
        password=params.get("password", ""),
        database=params.get("db") or params.get("database"),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(f"{query} LIMIT %s OFFSET %s", (limit, offset))
            rows = list(cur.fetchall())
    finally:
        conn.close()
    return rows, len(rows)


class SqlQuerySkill(BaseSkill):
    """Read-only SQL query helper across SQLite / Postgres / MySQL."""

    def __init__(self, controller=None):
        self.controller = controller

    @property
    def name(self) -> str:
        return "sql_query"

    @property
    def description(self) -> str:
        return (
            "Run a read-only SQL SELECT against SQLite, Postgres, or MySQL. "
            "Params: engine ('sqlite'|'postgres'|'mysql', default sqlite), "
            "db_path (sqlite), dsn/host/port/user/password/db (others), "
            "query (SELECT only), limit (default 100), offset (default 0)."
        )

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "engine": {"type": "string", "enum": ["sqlite", "postgres", "mysql"]},
                "db_path": {"type": "string"},
                "dsn": {"type": "string"},
                "host": {"type": "string"},
                "port": {"type": "integer"},
                "user": {"type": "string"},
                "password": {"type": "string"},
                "db": {"type": "string"},
                "query": {"type": "string"},
                "limit": {"type": "integer"},
                "offset": {"type": "integer"},
            },
            "required": ["query"],
        }

    @property
    def safety_tier(self) -> str:
        return "safe"

    async def execute(self, params: Dict[str, Any]) -> str:
        engine = (params.get("engine") or "sqlite").lower()
        query = (params.get("query") or "").strip().rstrip(";")
        try:
            limit = max(1, min(int(params.get("limit", 100)), 1000))
        except (TypeError, ValueError):
            limit = 100
        try:
            offset = max(0, int(params.get("offset", 0)))
        except (TypeError, ValueError):
            offset = 0
        if not query:
            return "Error: query is required."
        err = _validate_select(query)
        if err:
            return err
        try:
            if engine == "sqlite":
                rows, n = _run_sqlite(params.get("db_path", ""), query, limit, offset)
            elif engine == "postgres":
                rows, n = _run_postgres(params, query, limit, offset)
            elif engine == "mysql":
                rows, n = _run_mysql(params, query, limit, offset)
            else:
                return f"Error: unknown engine '{engine}' (sqlite|postgres|mysql)."
        except FileNotFoundError as e:
            return f"sql_query error: {e}"
        except Exception as e:
            return f"sql_query error: {e}"
        next_offset = offset + n if n == limit else None
        return json.dumps({
            "engine": engine,
            "rows": rows,
            "count": n,
            "limit": limit,
            "offset": offset,
            "next_offset": next_offset,
        }, default=str)

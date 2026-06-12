"""Database provider abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list[Any]]
    rowcount: int


class DBProvider(ABC):
    """Abstract database operations."""

    @abstractmethod
    async def connect(self, connection_string: str) -> bool:
        ...

    @abstractmethod
    async def disconnect(self) -> bool:
        ...

    @abstractmethod
    async def execute(self, query: str, params: tuple = ()) -> QueryResult:
        ...

    @abstractmethod
    async def fetch_one(self, query: str, params: tuple = ()) -> dict | None:
        ...

    @abstractmethod
    async def fetch_all(self, query: str, params: tuple = ()) -> list[dict]:
        ...

    @abstractmethod
    async def tables(self) -> list[str]:
        ...

    @abstractmethod
    async def describe_table(self, table: str) -> list[dict]:
        ...


class SQLiteProvider(DBProvider):
    """SQLite database provider."""

    def __init__(self):
        self._conn = None

    async def connect(self, connection_string: str) -> bool:
        import aiosqlite

        self._conn = await aiosqlite.connect(connection_string)
        self._conn.row_factory = aiosqlite.Row
        return True

    async def disconnect(self) -> bool:
        if self._conn:
            await self._conn.close()
            self._conn = None
        return True

    async def execute(self, query: str, params: tuple = ()) -> QueryResult:
        if not self._conn:
            raise RuntimeError("Not connected")
        cursor = await self._conn.execute(query, params)
        await self._conn.commit()
        return QueryResult(
            columns=[d[0] for d in cursor.description] if cursor.description else [],
            rows=[],
            rowcount=cursor.rowcount,
        )

    async def fetch_one(self, query: str, params: tuple = ()) -> dict | None:
        if not self._conn:
            raise RuntimeError("Not connected")
        cursor = await self._conn.execute(query, params)
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def fetch_all(self, query: str, params: tuple = ()) -> list[dict]:
        if not self._conn:
            raise RuntimeError("Not connected")
        cursor = await self._conn.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def tables(self) -> list[str]:
        rows = await self.fetch_all("SELECT name FROM sqlite_master WHERE type='table'")
        return [r["name"] for r in rows]

    async def describe_table(self, table: str) -> list[dict]:
        return await self.fetch_all(f"PRAGMA table_info({table})")


class PostgresProvider(DBProvider):
    """PostgreSQL database provider (asyncpg)."""

    def __init__(self):
        self._pool = None

    async def connect(self, connection_string: str) -> bool:
        import asyncpg

        self._pool = await asyncpg.create_pool(connection_string)
        return True

    async def disconnect(self) -> bool:
        if self._pool:
            await self._pool.close()
            self._pool = None
        return True

    async def execute(self, query: str, params: tuple = ()) -> QueryResult:
        if not self._pool:
            raise RuntimeError("Not connected")
        async with self._pool.acquire() as conn:
            result = await conn.execute(query, *params)
            # result is like "INSERT 0 1"
            parts = result.split()
            rowcount = int(parts[-1]) if parts else 0
            return QueryResult(columns=[], rows=[], rowcount=rowcount)

    async def fetch_one(self, query: str, params: tuple = ()) -> dict | None:
        if not self._pool:
            raise RuntimeError("Not connected")
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, *params)
            return dict(row) if row else None

    async def fetch_all(self, query: str, params: tuple = ()) -> list[dict]:
        if not self._pool:
            raise RuntimeError("Not connected")
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]

    async def tables(self) -> list[str]:
        rows = await self.fetch_all("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        return [r["tablename"] for r in rows]

    async def describe_table(self, table: str) -> list[dict]:
        return await self.fetch_all(
            """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = $1
            """,
            (table,),
        )


def create_provider(db_type: str) -> DBProvider:
    """Factory for database providers."""
    providers = {
        "sqlite": SQLiteProvider,
        "sqlite3": SQLiteProvider,
        "postgresql": PostgresProvider,
        "postgres": PostgresProvider,
    }
    cls = providers.get(db_type.lower())
    if not cls:
        raise ValueError(f"Unknown database type: {db_type}")
    return cls()

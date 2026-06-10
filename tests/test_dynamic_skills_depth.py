"""
P2: tests for the upgraded dynamic skills.

We exercise the SQLite path of the SQL skill with pagination, and we sanity
check that the unsupported-engine and missing-driver branches return clear
error messages instead of crashing.
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import tempfile
import unittest

from viki.skills.dynamic.sql_query_skill import SqlQuerySkill


def _run(coro):
    return asyncio.run(coro)


class TestSqlQuerySkill(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = os.path.join(self._td.name, "demo.sqlite")
        conn = sqlite3.connect(self.db)
        conn.execute("CREATE TABLE rows(id INT, label TEXT)")
        conn.executemany("INSERT INTO rows VALUES (?, ?)", [(i, f"row{i}") for i in range(10)])
        conn.commit()
        conn.close()

    def tearDown(self):
        try:
            self._td.cleanup()
        except Exception:
            pass

    def test_pagination_returns_next_offset(self):
        skill = SqlQuerySkill()
        out = _run(skill.execute({
            "engine": "sqlite",
            "db_path": self.db,
            "query": "SELECT id FROM rows ORDER BY id",
            "limit": 4,
            "offset": 0,
        }))
        data = json.loads(out)
        self.assertEqual(data["count"], 4)
        self.assertEqual(data["limit"], 4)
        self.assertEqual(data["offset"], 0)
        self.assertEqual(data["next_offset"], 4)

    def test_pagination_terminates_when_no_more_rows(self):
        skill = SqlQuerySkill()
        out = _run(skill.execute({
            "engine": "sqlite",
            "db_path": self.db,
            "query": "SELECT id FROM rows ORDER BY id",
            "limit": 4,
            "offset": 8,
        }))
        data = json.loads(out)
        self.assertEqual(data["count"], 2)
        self.assertIsNone(data["next_offset"])

    def test_blocks_write_query(self):
        skill = SqlQuerySkill()
        out = _run(skill.execute({
            "engine": "sqlite",
            "db_path": self.db,
            "query": "DELETE FROM rows WHERE id = 1",
        }))
        self.assertIn("Error", out)

    def test_unknown_engine(self):
        skill = SqlQuerySkill()
        out = _run(skill.execute({"engine": "oracle", "query": "SELECT 1"}))
        self.assertIn("unknown engine", out)

    def test_missing_driver_returns_friendly_error(self):
        skill = SqlQuerySkill()
        out = _run(skill.execute({
            "engine": "postgres",
            "host": "localhost",
            "db": "x",
            "query": "SELECT 1",
        }))
        self.assertIn("postgres engine", out)


if __name__ == "__main__":
    unittest.main()

"""
Phase 4: smoke tests for dynamic skills.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import tempfile
import unittest

from viki.skills.dynamic.aws_console_skill import AwsConsoleSkill
from viki.skills.dynamic.kubernetes_ctl_skill import KubernetesCtlSkill
from viki.skills.dynamic.sql_query_skill import SqlQuerySkill


def _run(coro):
    return asyncio.run(coro)


class TestSqlQuerySkill(unittest.TestCase):
    def setUp(self):
        # Use ignore_cleanup_errors to dodge Windows sqlite WAL file locks.
        self._td = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.path = os.path.join(self._td.name, "t.db")
        with sqlite3.connect(self.path) as conn:
            conn.execute("CREATE TABLE t(id INTEGER, name TEXT)")
            conn.executemany("INSERT INTO t(id, name) VALUES(?, ?)", [(1, "a"), (2, "b")])
            conn.commit()

    def tearDown(self):
        try:
            self._td.cleanup()
        except Exception:
            pass

    def test_select_query_succeeds(self):
        skill = SqlQuerySkill()
        out = _run(skill.execute({"db_path": self.path, "query": "SELECT * FROM t"}))
        self.assertIn('"name": "a"', out)

    def test_write_query_rejected(self):
        skill = SqlQuerySkill()
        out = _run(skill.execute({"db_path": self.path, "query": "INSERT INTO t VALUES (1)"}))
        self.assertIn("Error", out)


class TestAwsConsoleSkill(unittest.TestCase):
    def test_rejects_write_operation(self):
        skill = AwsConsoleSkill()
        out = _run(skill.execute({"service": "s3", "operation": "create_bucket"}))
        self.assertIn("Error", out)


class TestKubernetesCtlSkill(unittest.TestCase):
    def test_rejects_unknown_verb(self):
        skill = KubernetesCtlSkill()
        out = _run(skill.execute({"verb": "delete"}))
        self.assertIn("Error", out)


if __name__ == "__main__":
    unittest.main()

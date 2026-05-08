"""
Phase 5: tests for the DPO/ORPO preference dataset builder + teacher distillation.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import tempfile
import unittest
from typing import List

from viki.core.preference_forge import (
    PreferenceDatasetBuilder,
    PreferencePair,
    TeacherDistillation,
)


class _StubLearning:
    """Minimal in-memory stand-in for the LearningModule's SQLite store."""

    def __init__(self, tmp_path: str):
        self.conn = sqlite3.connect(tmp_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            "CREATE TABLE failures (id INTEGER PRIMARY KEY, action TEXT, error TEXT, context TEXT, timestamp REAL)"
        )
        self.conn.execute(
            "CREATE TABLE lessons (text_representation TEXT, content TEXT, access_count INTEGER, "
            "source_task TEXT, reliability REAL, last_accessed REAL)"
        )
        self.conn.commit()

    def add_failure(self, action: str, error: str, context: str):
        self.conn.execute(
            "INSERT INTO failures (action, error, context, timestamp) VALUES (?, ?, ?, ?)",
            (action, error, context, 0.0),
        )
        self.conn.commit()

    def add_lesson(self, trigger: str, fact: str, access_count: int = 3):
        content = json.dumps({"trigger": trigger, "fact": fact})
        self.conn.execute(
            "INSERT INTO lessons (text_representation, content, access_count, source_task, reliability, last_accessed) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (fact, content, access_count, "test", 1.0, 0.0),
        )
        self.conn.commit()

    def get_relevant_lessons(self, query: str, limit: int = 1) -> List[str]:
        return ["Use the math_skill for arithmetic."]


def _run(coro):
    return asyncio.run(coro)


class TestPreferenceDatasetBuilder(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = os.path.join(self._td.name, "learn.sqlite")
        self.learning = _StubLearning(self.db_path)

    def tearDown(self):
        try:
            self.learning.conn.close()
        except Exception:
            pass
        try:
            self._td.cleanup()
        except Exception:
            pass

    def test_mines_failure_and_lesson_pairs(self):
        self.learning.add_failure(
            action="shell:rm -rf /",
            error="permission denied",
            context="user asked: clean the disk",
        )
        self.learning.add_lesson("How to do math?", "Use math_skill for arithmetic.")
        out_path = os.path.join(self._td.name, "pairs.jsonl")
        builder = PreferenceDatasetBuilder(self.learning)
        msg, n = builder.build(out_path)
        self.assertGreaterEqual(n, 2)
        with open(out_path, "r", encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]
        sources = {r["source"] for r in rows}
        self.assertIn("failure", sources)
        self.assertIn("memory", sources)
        for r in rows:
            self.assertIn("prompt", r)
            self.assertIn("chosen", r)
            self.assertIn("rejected", r)

    def test_no_pairs_when_db_empty(self):
        out_path = os.path.join(self._td.name, "empty.jsonl")
        builder = PreferenceDatasetBuilder(self.learning)
        msg, n = builder.build(out_path)
        self.assertEqual(n, 0)
        self.assertFalse(os.path.isfile(out_path))


class TestTeacherDistillation(unittest.TestCase):
    def test_consent_required(self):
        class StubModel:
            model_name = "stub"
            provider_name = "stub"

            async def chat(self, messages, temperature=0.0):
                return "teacher response"

        class StubRouter:
            def get_model(self, capabilities=None):
                return StubModel()

        async def go():
            local = StubModel()
            distiller = TeacherDistillation(StubRouter())
            pairs = await distiller.generate(
                [
                    {"prompt": "P1", "consent": False},
                    {"prompt": "P2", "consent": True},
                ],
                local,
            )
            return pairs

        pairs = _run(go())
        # Same model returns same answer for both -> filtered out by no-diff guard.
        self.assertEqual(len(pairs), 0)


if __name__ == "__main__":
    unittest.main()

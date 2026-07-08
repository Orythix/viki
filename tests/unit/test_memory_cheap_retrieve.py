"""
Cheap-retrieve fast path.

For trivial conversational input, `MemoryStack.get_full_context` must NOT
invoke the encoder, AND `LearningModule.get_relevant_lessons` must short-
circuit to an empty list.
"""

from __future__ import annotations

import tempfile
import unittest
from unittest.mock import MagicMock, patch

from viki.core.utils.trivial_input import is_trivial_input


class TestTrivialInputHelper(unittest.TestCase):
    def test_greetings_are_trivial(self):
        self.assertTrue(is_trivial_input("hi"))
        self.assertTrue(is_trivial_input("hello"))
        self.assertTrue(is_trivial_input("thanks"))
        self.assertTrue(is_trivial_input("good morning"))
        self.assertTrue(is_trivial_input("hello viki"))
        self.assertTrue(is_trivial_input("bye"))
        self.assertTrue(is_trivial_input("ok"))

    def test_meaningful_short_input_is_not_trivial(self):
        # These are short but NOT greetings — we must not strip context.
        self.assertFalse(is_trivial_input("Another plan."))
        self.assertFalse(is_trivial_input("retry"))
        self.assertFalse(is_trivial_input("again"))

    def test_long_input_is_not_trivial(self):
        self.assertFalse(
            is_trivial_input(
                "hello, can you help me write a python script that processes 100 files?"
            )
        )

    def test_task_request_is_not_trivial(self):
        self.assertFalse(is_trivial_input("run pytest"))
        self.assertFalse(is_trivial_input("fix the bug"))
        self.assertFalse(is_trivial_input("open chrome"))

    def test_question_pings_are_not_trivial(self):
        self.assertFalse(is_trivial_input("why?"))
        self.assertFalse(is_trivial_input("how?"))

    def test_empty_is_trivial(self):
        self.assertTrue(is_trivial_input(""))
        self.assertTrue(is_trivial_input("   "))


class TestLearningCheapRetrieve(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)

    def tearDown(self):
        try:
            self._td.cleanup()
        except Exception:
            pass

    def test_trivial_input_returns_empty_lessons_without_db_hit(self):
        from viki.core.knowledge_ingestion import LearningModule

        lm = LearningModule(self._td.name)

        # The cheap-retrieve fast path must NOT touch the encoder property.
        with patch("viki.core.embeddings.get_encoder") as mock_get:
            result = lm.get_relevant_lessons("hi")
            self.assertEqual(result, [])
            mock_get.assert_not_called()

    def test_non_trivial_input_does_query_db(self):
        from viki.core.knowledge_ingestion import LearningModule

        lm = LearningModule(self._td.name)
        # No lessons in the DB; should still return [] but exercises the
        # SQL path. We only assert it doesn't crash.
        result = lm.get_relevant_lessons("please refactor the database layer")
        self.assertEqual(result, [])


class TestMemoryCheapRetrieve(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)

    def tearDown(self):
        try:
            self._td.cleanup()
        except Exception:
            pass

    def test_trivial_input_skips_semantic_query(self):
        from viki.core.knowledge_ingestion import LearningModule
        from viki.core.memory import HierarchicalMemory

        learning = LearningModule(self._td.name)
        config = {
            "system": {"data_dir": self._td.name},
            "memory": {"short_term_limit": 15},
        }
        ms = HierarchicalMemory(config, learning_module=learning)

        # Stub episodic.retrieve_context so we can verify the kwargs.
        recorded = {}

        def _capture(query, limit=3, cheap=False, **kw):
            recorded["cheap"] = cheap
            recorded["limit"] = limit
            return []

        ms.episodic.retrieve_context = _capture
        # Stub semantic so we can ensure it's not invoked.
        if ms.semantic is not None:
            ms.semantic.get_relevant_lessons = MagicMock(return_value=["should-not-be-called"])

        ctx = ms.get_full_context("hi")
        self.assertTrue(recorded.get("cheap") is True)
        self.assertEqual(ctx.get("semantic"), [])
        if ms.semantic is not None:
            ms.semantic.get_relevant_lessons.assert_not_called()


if __name__ == "__main__":
    unittest.main()

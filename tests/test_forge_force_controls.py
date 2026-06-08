"""
P1: tests for operator-initiated forge promote/rollback.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from types import SimpleNamespace

from core.continuous_learning import ContinuousLearner


class _StubLearning:
    def get_total_lesson_count(self):
        return 0


def _stub_controller(data_dir: str) -> SimpleNamespace:
    return SimpleNamespace(
        settings={"system": {"data_dir": data_dir}},
        models_config={"models": {"default": "viki-base"}},
        learning=_StubLearning(),
        skill_registry=None,
    )


class TestForceControls(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.controller = _stub_controller(self._td.name)
        self.learner = ContinuousLearner(self.controller)

    def tearDown(self):
        try:
            self._td.cleanup()
        except Exception:
            pass

    def test_force_promote_records_history(self):
        result = self.learner.force_promote("viki-evolved", operator="alice")
        self.assertTrue(result["ok"])
        self.assertEqual(result["new_default"], "viki-evolved")
        history = self.learner._promotion_state["history"]
        self.assertEqual(history[-1]["decision"], "force_promoted")
        self.assertEqual(history[-1]["operator"], "alice")

    def test_force_rollback_to_previous(self):
        self.learner.force_promote("viki-evolved")
        result = self.learner.force_rollback()
        self.assertTrue(result["ok"])
        self.assertEqual(result["new_default"], "viki-base")

    def test_force_rollback_with_explicit_target(self):
        self.learner.force_promote("viki-evolved")
        result = self.learner.force_rollback("viki-archived")
        self.assertTrue(result["ok"])
        self.assertEqual(result["new_default"], "viki-archived")

    def test_rollback_without_history_fails(self):
        result = self.learner.force_rollback()
        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()

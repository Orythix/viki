"""
P2 tier-1: ContinuousLearner integration tests.

Covers:
- _capability_index_for() actually returns a numeric index when eval results
  exist on disk (the P0 kwarg-bug fix continues to hold);
- promotion path doesn't hard-fail when there are no eval results.
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from types import SimpleNamespace

from viki.core.continuous_learning import ContinuousLearner


def _run(coro):
    return asyncio.run(coro)


def _write_results(data_dir: str, suite: str, results, metadata=None):
    suite_dir = os.path.join(data_dir, "eval_results", suite)
    os.makedirs(suite_dir, exist_ok=True)
    path = os.path.join(suite_dir, "001.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        if metadata:
            f.write(json.dumps({"__metadata__": True, **metadata}) + "\n")
        for r in results:
            f.write(json.dumps(r) + "\n")


class _StubScorecard:
    def __init__(self):
        self.metrics = {}
    def get_summary(self, model=None):
        return {}
    def record_metric(self, *a, **kw):
        pass


class _StubController:
    def __init__(self, data_dir, default_model="local-7b"):
        self.settings = {
            "system": {"data_dir": data_dir},
            "forge": {
                "promotion_min_index_delta": 0.01,
                "promotion_min_consecutive_passes": 2,
                "capability_index_min_tasks": 0,
            },
        }
        self.models_config = {"models": {"default": default_model}}
        self.scorecard = _StubScorecard()


class TestContinuousLearnerIntegration(unittest.TestCase):
    def test_capability_index_returns_number(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            _write_results(td, "humaneval_plus",
                           [{"task_id": f"t{i}", "score": 1.0, "passed": True} for i in range(5)],
                           metadata={"model_profile": "local-7b", "model_name": "local-7b:latest"})
            ctrl = _StubController(td)
            cl = ContinuousLearner(ctrl)
            score = _run(cl._capability_index_for("local-7b"))
            self.assertIsNotNone(score)
            self.assertIsInstance(score, float)
            self.assertGreater(score, 0.0)

    def test_capability_index_handles_missing_results(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            ctrl = _StubController(td)
            cl = ContinuousLearner(ctrl)
            score = _run(cl._capability_index_for("local-7b"))
            self.assertIsNone(score)


if __name__ == "__main__":
    unittest.main()

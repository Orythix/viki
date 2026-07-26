"""
Phase 5: tests for eval-gated auto-promotion + auto-rollback in
ContinuousLearner, plus per-model scorecard segmentation.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from types import SimpleNamespace

from viki.core.continuous_learning import ContinuousLearner
from viki.core.scorecard import IntelligenceScorecard


def _run(coro):
    return asyncio.run(coro)


class _StubLearning:
    def get_total_lesson_count(self):
        return 0

    def save_lesson(self, **kwargs):
        return None


def _stub_controller(data_dir: str, settings: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        settings={"system": {"data_dir": data_dir, **(settings or {})}},
        models_config={"models": {"default": "viki-base"}},
        models_config_path=os.path.join(data_dir, "models.yaml"),
        learning=_StubLearning(),
        skill_registry=None,
    )


class TestPromotionGate(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.data_dir = self._td.name

    def tearDown(self):
        try:
            self._td.cleanup()
        except Exception:
            pass

    def test_promotes_after_consecutive_passes(self):
        controller = _stub_controller(
            self.data_dir,
            {"promotion_min_index_delta": 0.05, "promotion_min_consecutive_passes": 2},
        )
        learner = ContinuousLearner(controller)

        scores = {"viki-base": 0.40, "viki-evolved": 0.55}

        async def fake_compute(name):
            return scores.get(name, 0.0)

        learner._capability_index_for = fake_compute  # type: ignore

        # First eval pass: increments counter but no promotion yet.
        promoted = _run(learner.maybe_promote("viki-evolved"))
        self.assertFalse(promoted)
        # Second eval pass: should promote.
        promoted = _run(learner.maybe_promote("viki-evolved"))
        self.assertTrue(promoted)
        self.assertEqual(controller.models_config["models"]["default"], "viki-evolved")

    def test_rolls_back_on_regression(self):
        controller = _stub_controller(
            self.data_dir,
            {"promotion_min_index_delta": 0.05, "promotion_min_consecutive_passes": 1},
        )
        learner = ContinuousLearner(controller)
        learner._promotion_state["current_default"] = "viki-base"

        scores = {"viki-base": 0.50, "viki-bad": 0.10}

        async def fake_compute(name):
            return scores.get(name, 0.0)

        learner._capability_index_for = fake_compute  # type: ignore

        promoted = _run(learner.maybe_promote("viki-bad"))
        self.assertFalse(promoted)
        # On regression we explicitly call rollback to the previous default.
        self.assertEqual(controller.models_config["models"]["default"], "viki-base")

    def test_persists_state(self):
        controller = _stub_controller(
            self.data_dir,
            {"promotion_min_index_delta": 0.05, "promotion_min_consecutive_passes": 2},
        )
        learner = ContinuousLearner(controller)

        scores = {"viki-base": 0.40, "viki-evolved": 0.55}

        async def fake_compute(name):
            return scores.get(name, 0.0)

        learner._capability_index_for = fake_compute  # type: ignore
        _run(learner.maybe_promote("viki-evolved"))
        self.assertTrue(os.path.isfile(learner.promotion_state_path))
        with open(learner.promotion_state_path) as f:
            state = json.load(f)
        self.assertIn("consecutive_passes", state)

    def test_capability_index_lookup_uses_positional_kwarg(self):
        """
        P0 regression: ContinuousLearner._capability_index_for previously called
        `CapabilityIndex(eval_results_dir=...)` which is not a valid kwarg.
        The except-block swallowed the TypeError, so promotion silently always
        returned None. This test forces the real (non-mocked) path and asserts
        a numeric score is returned.
        """
        controller = _stub_controller(self.data_dir)
        learner = ContinuousLearner(controller)

        suite_dir = os.path.join(self.data_dir, "eval_results", "humaneval_plus")
        os.makedirs(suite_dir, exist_ok=True)
        with open(os.path.join(suite_dir, "run1.jsonl"), "w", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "__metadata__": True,
                        "model_profile": "any-model",
                        "model_name": "any-model:latest",
                        "air_gap": True,
                    }
                )
                + "\n"
            )
            f.write(
                json.dumps(
                    {
                        "task_id": "t1",
                        "score": 1.0,
                        "passed": True,
                    }
                )
                + "\n"
            )
            f.write(
                json.dumps(
                    {
                        "task_id": "t2",
                        "score": 1.0,
                        "passed": True,
                    }
                )
                + "\n"
            )

        score = _run(learner._capability_index_for("any-model"))
        self.assertIsNotNone(score, "capability index should compute, not silently fail")
        self.assertGreaterEqual(score, 0.0)

    def test_raw_model_tag_retargets_viki_evolved_profile(self):
        controller = _stub_controller(self.data_dir)
        controller.models_config = {
            "models": {
                "default": "gemma4",
                "profiles": {
                    "gemma4": {"model_name": "gemma4:latest"},
                    "viki-evolved": {"model_name": "old-forge:latest"},
                },
            }
        }
        with open(controller.models_config_path, "w", encoding="utf-8") as f:
            import yaml

            yaml.safe_dump(controller.models_config, f)

        learner = ContinuousLearner(controller)
        result = learner.force_promote("viki-neural-forge", operator="alice")

        self.assertTrue(result["ok"])
        self.assertEqual(controller.models_config["models"]["default"], "viki-evolved")
        self.assertEqual(
            controller.models_config["models"]["profiles"]["viki-evolved"]["model_name"],
            "viki-neural-forge",
        )


class TestScorecardSegmentation(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)

    def tearDown(self):
        try:
            self._td.cleanup()
        except Exception:
            pass

    def test_per_model_summary(self):
        sc = IntelligenceScorecard(self._td.name)
        sc.record_metric("reliability_rate", 0.9, model="viki-base")
        sc.record_metric("reliability_rate", 0.7, model="viki-evolved")
        sc.record_metric("reliability_rate", 0.8, model="viki-base")
        seg = sc.get_segmented_summary()
        self.assertIn("_all_", seg)
        self.assertIn("viki-base", seg)
        self.assertIn("viki-evolved", seg)
        self.assertAlmostEqual(seg["viki-base"]["reliability_rate"], 0.85, places=4)
        self.assertAlmostEqual(seg["viki-evolved"]["reliability_rate"], 0.7, places=4)


if __name__ == "__main__":
    unittest.main()

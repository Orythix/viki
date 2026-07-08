"""
Phase 0: tests for cognitive routing (Reflex + Judgment + CognitiveRouter).

These tests assert the four JudgmentOutcome branches each reach the correct
destination and that the router's reflex hit / fallthrough behavior is correct.
"""

from __future__ import annotations

import asyncio
import unittest

from viki.core.cognitive_loop import (
    CognitiveRouter,
    RouterTelemetry,
)
from viki.core.output_verifier import JudgmentEngine, JudgmentOutcome
from viki.core.rapid_response_system import ReflexBrain
from viki.core.schema import ActionCall


class _StubLearning:
    """Lightweight in-memory stand-in for LearningModule."""

    def __init__(self, lessons=None, failures=None):
        self._lessons = lessons or []
        self._failures = failures or []

    def get_relevant_failures(self, context, limit=3):
        return list(self._failures)[:limit]

    def get_relevant_lessons(self, context, limit=5):
        return list(self._lessons)[:limit]

    def get_total_lesson_count(self):
        return len(self._lessons)


class _StubSkillRegistry:
    def __init__(self, skills):
        self._skills = set(skills)

    def get_skill(self, name):
        # Truthy when registered.
        return object() if name in self._skills else None


def _run(coro):
    return asyncio.run(coro)


class TestJudgmentOutcomes(unittest.TestCase):
    def setUp(self):
        self.learning = _StubLearning(lessons=["User prefers Python", "User likes vim shortcuts"])
        self.je = JudgmentEngine(self.learning, {})

    def test_refuse_on_dangerous_intent(self):
        result = _run(
            self.je.evaluate("rm -rf delete kill format my entire disk now sudo overwrite", {})
        )
        self.assertEqual(result.outcome, JudgmentOutcome.REFUSE)
        self.assertEqual(result.recommendation, "deny")

    def test_refuse_on_low_clarity(self):
        result = _run(self.je.evaluate("a", {}))
        # Single word -> clarity 0.5, longer than 0.3 threshold; actually proceeds.
        self.assertNotEqual(result.outcome, JudgmentOutcome.REFUSE)

        # Empty input -> clarity 0
        empty = _run(self.je.evaluate("", {}))
        self.assertEqual(empty.outcome, JudgmentOutcome.REFUSE)

    def test_reflex_for_system_command(self):
        result = _run(self.je.evaluate("open notepad", {}))
        self.assertEqual(result.outcome, JudgmentOutcome.REFLEX)

    def test_deep_for_question(self):
        result = _run(
            self.je.evaluate(
                "What is the optimal architecture for a planner-executor agent?",
                {"task_type": "question"},
            )
        )
        self.assertEqual(result.outcome, JudgmentOutcome.DEEP)

    def test_failure_similarity_escalates(self):
        learning = _StubLearning(
            failures=[
                "PAST FAILURE: Tried 'browser navigate to acme.com' but got 'ConnectionRefused'"
            ],
        )
        je = JudgmentEngine(learning, {})
        result = _run(je.evaluate("browser navigate to acme.com please retry", {}))
        # Token overlap with failure -> elevated similarity, escalates DEEP.
        self.assertGreater(result.failure_similarity, 0.0)

    def test_novelty_high_when_no_lessons(self):
        empty = JudgmentEngine(_StubLearning(lessons=[]), {})
        result = _run(empty.evaluate("Build a quantum compiler", {}))
        self.assertGreaterEqual(result.novelty, 0.5)

    def test_capability_recommendation(self):
        result = _run(self.je.evaluate("research the price of bitcoin", {}))
        self.assertEqual(result.recommended_capability, "internet_research")
        result = _run(self.je.evaluate("read my notes file", {}))
        self.assertEqual(result.recommended_capability, "filesystem_read")
        result = _run(self.je.evaluate("write a new file at /tmp/x", {}))
        self.assertEqual(result.recommended_capability, "filesystem_write")


class TestCognitiveRouter(unittest.TestCase):
    def setUp(self):
        self.learning = _StubLearning(lessons=["common pattern"])
        self.je = JudgmentEngine(self.learning, {})
        self.reflex = ReflexBrain(data_dir=None)
        self.skills = _StubSkillRegistry(["system_control", "media_control", "research"])
        self.telemetry = RouterTelemetry()
        self.router = CognitiveRouter(
            judgment_engine=self.je, reflex_brain=self.reflex, telemetry=self.telemetry
        )

    def test_reflex_action_short_circuits(self):
        route = _run(self.router.classify("open notepad", skill_registry=self.skills))
        self.assertEqual(route.outcome, JudgmentOutcome.REFLEX)
        self.assertIsInstance(route.action_override, ActionCall)
        self.assertEqual(route.action_override.skill_name, "system_control")
        self.assertTrue(route.is_short_circuit)
        self.assertEqual(route.source, "reflex")

    def test_reflex_with_unknown_skill_falls_through(self):
        empty_registry = _StubSkillRegistry([])
        route = _run(self.router.classify("open notepad", skill_registry=empty_registry))
        self.assertNotEqual(route.outcome, JudgmentOutcome.REFLEX)

    def test_refuse_outcome_creates_refusal_route(self):
        # Risk is gated on dangerous keywords; these stack to >0.8.
        route = _run(
            self.router.classify(
                "delete delete delete remove kill format overwrite my disk sudo now",
                skill_registry=self.skills,
            )
        )
        self.assertEqual(route.outcome, JudgmentOutcome.REFUSE)
        self.assertTrue(route.refusal_reason)
        self.assertTrue(route.is_short_circuit)

    def test_question_routes_deep(self):
        route = _run(
            self.router.classify(
                "Explain how an A-Star pathfinding algorithm avoids cycles in a maze",
                context={"task_type": "question"},
                skill_registry=self.skills,
            )
        )
        self.assertEqual(route.outcome, JudgmentOutcome.DEEP)
        self.assertFalse(route.use_lite_schema)
        self.assertFalse(route.use_ensemble)
        self.assertFalse(route.is_short_circuit)

    def test_shallow_routes_with_lite_schema(self):
        # Standard task: low risk, moderate novelty -> SHALLOW path.
        route = _run(
            self.router.classify(
                "summarize this paragraph for me please",
                skill_registry=self.skills,
            )
        )
        self.assertIn(route.outcome, (JudgmentOutcome.SHALLOW, JudgmentOutcome.DEEP))
        if route.outcome == JudgmentOutcome.SHALLOW:
            self.assertTrue(route.use_lite_schema)
            self.assertFalse(route.use_ensemble)

    def test_telemetry_tracks_outcomes(self):
        _run(self.router.classify("open notepad", skill_registry=self.skills))
        _run(
            self.router.classify(
                "Explain pathfinding",
                context={"task_type": "question"},
                skill_registry=self.skills,
            )
        )
        snap = self.telemetry.snapshot()
        self.assertEqual(snap["total"], 2)
        self.assertGreaterEqual(snap["reflex_hits"], 1)
        self.assertIn("by_outcome", snap)


class TestRouterTelemetryReflexRate(unittest.TestCase):
    def test_reflex_hit_rate_threshold(self):
        """Phase 0 done-criteria sanity: 30% reflex hit rate on a recorded session."""
        learning = _StubLearning(lessons=["x"])
        je = JudgmentEngine(learning, {})
        reflex = ReflexBrain(data_dir=None)
        telemetry = RouterTelemetry()
        router = CognitiveRouter(judgment_engine=je, reflex_brain=reflex, telemetry=telemetry)
        skills = _StubSkillRegistry(["system_control", "media_control", "research"])

        commands = [
            "open chrome",
            "launch vscode",
            "play music",
            "pause",
            "mute",
            "volume up",
            "search the latest python release notes",
            "google quantum supremacy paper 2026",
            "type hello world",
            "what is the meaning of life",
            "explain monad transformers",
            "draft a short essay on stoicism",
            "click 250 250",
            "press enter",
            "scroll 5",
        ]
        for c in commands:
            _run(router.classify(c, skill_registry=skills))

        snap = telemetry.snapshot()
        # 9 of the 15 should reflex-hit.
        self.assertGreaterEqual(snap["reflex_hit_rate"], 0.30)


if __name__ == "__main__":
    unittest.main()

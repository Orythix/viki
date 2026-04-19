"""Unit tests for VIKIController._classify_task and JudgmentEngine research heuristics."""

import asyncio
import unittest
from unittest.mock import MagicMock

from viki.core.controller import VIKIController
from viki.core.judgment import JudgmentEngine


class TestClassifyTask(unittest.TestCase):
    def _classify(self, text: str) -> str:
        # _classify_task does not use instance state
        return VIKIController._classify_task(None, text)

    def test_question_with_leading_whitespace(self):
        self.assertEqual(self._classify("   what is 2+2?"), "reasoning")

    def test_question_without_question_mark(self):
        self.assertEqual(self._classify("what is 2+2"), "reasoning")

    def test_plain_general(self):
        self.assertEqual(self._classify("hello there"), "general")

    def test_compute_style_general(self):
        self.assertEqual(self._classify("Compute 2+2"), "general")


class TestJudgmentWhatIsHeuristic(unittest.TestCase):
    def test_what_is_arithmetic_skips_internet_research_cap(self):
        je = JudgmentEngine(MagicMock(), {})
        r = asyncio.run(je.evaluate("what is 2+2?", {}))
        self.assertIsNone(r.recommended_capability)

    def test_what_is_encyclopedic_sets_internet_research(self):
        je = JudgmentEngine(MagicMock(), {})
        r = asyncio.run(je.evaluate("what is quantum computing?", {}))
        self.assertEqual(r.recommended_capability, "internet_research")

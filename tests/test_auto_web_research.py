"""Unit tests for automatic web research when the model appears uncertain."""

from __future__ import annotations

import unittest

from viki.core.orchestrator import VIKIController


class TestAutoWebResearchHeuristics(unittest.TestCase):
    def setUp(self):
        self.ctrl = VIKIController.__new__(VIKIController)
        self.ctrl.settings = {"system": {"auto_web_research_when_uncertain": True}}
        self.ctrl.air_gap = False
        self.ctrl.shadow_mode = False

    def test_setting_enabled_respects_air_gap_and_shadow(self):
        self.assertTrue(self.ctrl._auto_web_research_setting_enabled())
        self.ctrl.air_gap = True
        self.assertFalse(self.ctrl._auto_web_research_setting_enabled())
        self.ctrl.air_gap = False
        self.ctrl.shadow_mode = True
        self.assertFalse(self.ctrl._auto_web_research_setting_enabled())

    def test_setting_disabled_in_yaml(self):
        self.ctrl.shadow_mode = False
        self.ctrl.air_gap = False
        self.ctrl.settings = {"system": {"auto_web_research_when_uncertain": False}}
        self.assertFalse(self.ctrl._auto_web_research_setting_enabled())

    def test_knowledge_gap_markers(self):
        self.assertTrue(
            self.ctrl._response_indicates_knowledge_gap("I'm not sure when that treaty was signed.")
        )
        self.assertTrue(
            self.ctrl._response_indicates_knowledge_gap("I don't know the stock price.")
        )
        self.assertFalse(
            self.ctrl._response_indicates_knowledge_gap(
                "The capital of France is Paris, known for the Eiffel Tower."
            )
        )

    def test_skips_when_already_has_web_block(self):
        self.assertFalse(
            self.ctrl._response_indicates_knowledge_gap(
                "Here is what I found.\n\n---\n**Web lookup (automatic)**\n..."
            )
        )


if __name__ == "__main__":
    unittest.main()

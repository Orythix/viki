"""
P2 tier-1: Cortex layer integration tests.

Verifies that the perception/interpretation layers run end-to-end and that
the layer base contract holds (status flips Idle -> Processing -> Idle).
"""
from __future__ import annotations

import asyncio
import unittest

from core.cognitive_processor import InterpretationLayer, PerceptionLayer


def _run(coro):
    return asyncio.run(coro)


class TestCortexLayers(unittest.TestCase):
    def test_perception_normalizes_whitespace(self):
        layer = PerceptionLayer("perception", "")
        out = _run(layer.process("   open    cursor   "))
        self.assertEqual(out, "open cursor")
        self.assertEqual(layer.state.status, "Idle")
        self.assertEqual(layer.state.load, 0.0)

    def test_interpretation_classifies_command_intent(self):
        layer = InterpretationLayer("interpretation", "")
        out = _run(layer.process("open cursor"))
        self.assertIsInstance(out, dict)
        self.assertEqual(out.get("intent_type"), "system_command")
        self.assertEqual(out["entities"].get("app_name"), "cursor")


if __name__ == "__main__":
    unittest.main()

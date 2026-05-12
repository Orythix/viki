"""
Greeting / ack / farewell reflexes return canned replies without invoking the
LLM. This is the cheapest possible "hello viki" path.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from viki.core.rapid_response_system import ReflexBrain


class TestConversationalReflex(unittest.TestCase):
    def setUp(self):
        self.brain = ReflexBrain(data_dir=None)

    def test_hello_viki_returns_canned_reply(self):
        reply, action = self.brain.think("hello viki")
        self.assertIsNotNone(reply, "expected a canned greeting reply")
        self.assertIsNone(action)
        self.assertGreater(len(reply), 0)

    def test_hi_returns_canned_reply(self):
        reply, action = self.brain.think("hi")
        self.assertIsNotNone(reply)
        self.assertIsNone(action)

    def test_hey_there_returns_canned_reply(self):
        reply, _ = self.brain.think("hey there")
        self.assertIsNotNone(reply)

    def test_thanks_returns_canned_reply(self):
        reply, action = self.brain.think("thanks")
        self.assertIsNotNone(reply)
        self.assertIsNone(action)

    def test_bye_returns_canned_reply(self):
        reply, action = self.brain.think("bye")
        self.assertIsNotNone(reply)
        self.assertIsNone(action)

    def test_good_morning_substitutes_tod(self):
        reply, _ = self.brain.think("good morning")
        self.assertIsNotNone(reply)
        self.assertIn("morning", reply.lower())

    def test_real_question_does_not_trigger_canned(self):
        reply, action = self.brain.think("what is the capital of france?")
        self.assertIsNone(reply)
        self.assertIsNone(action)

    def test_long_input_does_not_trigger_canned(self):
        long_input = "hi " + ("can you help me with this very long task " * 5)
        reply, action = self.brain.think(long_input)
        self.assertIsNone(reply)

    def test_reflex_does_not_call_model_router(self):
        """Greetings must never even reach a model router."""
        with patch("viki.core.rapid_response_system.viki_logger"):
            with patch("viki.core.inference_gateway.ModelRouter", MagicMock()) as router_cls:
                router = router_cls.return_value
                reply, _ = self.brain.think("hello viki")
                self.assertIsNotNone(reply)
                router.get_model.assert_not_called()


if __name__ == "__main__":
    unittest.main()

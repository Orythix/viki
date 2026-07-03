"""
P0 regression: ComputerUseSkill must NOT silently click the screen center
when no real UI grounding is available.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from viki.skills.builtins.computer_use_skill import ComputerUseSkill, UIElement


def _run(coro):
    return asyncio.run(coro)


class TestComputerUseGrounding(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.skill = ComputerUseSkill(controller=None, data_dir=self._td.name)

    def tearDown(self):
        try:
            self._td.cleanup()
        except Exception:
            pass

    def test_low_confidence_match_is_rejected(self):
        # Inject a plausibly-matching but low-confidence element.
        self.skill._last_screenshot = os.path.join(self._td.name, "fake.png")
        # Need a placeholder file so _capture_screenshot is not called.
        open(self.skill._last_screenshot, "wb").close()
        self.skill._last_elements = [
            UIElement(label="login button", bbox=(100, 100, 200, 150), confidence=0.1)
        ]
        result = _run(self.skill._do_click_element({"label": "login button"}))
        payload = json.loads(result)
        self.assertEqual(payload["status"], "rejected")
        self.assertEqual(payload["reason"], "low_confidence")

    def test_degenerate_bbox_is_rejected(self):
        self.skill._last_screenshot = os.path.join(self._td.name, "fake.png")
        open(self.skill._last_screenshot, "wb").close()
        # Above the confidence floor but a 1-pixel box → reject.
        self.skill._last_elements = [UIElement(label="ghost", bbox=(0, 0, 0, 0), confidence=0.99)]
        result = _run(self.skill._do_click_element({"label": "ghost"}))
        payload = json.loads(result)
        self.assertEqual(payload["status"], "rejected")
        self.assertEqual(payload["reason"], "degenerate_bbox")

    def test_no_grounder_returns_empty(self):
        # No controller, no env var → grounding must be empty (not a
        # full-screen dummy element as before).
        with patch.object(
            self.skill, "_capture_screenshot", return_value=os.path.join(self._td.name, "x.png")
        ):
            with open(os.path.join(self._td.name, "x.png"), "wb") as f:
                f.write(b"")
            elements = _run(self.skill._ground_elements(os.path.join(self._td.name, "x.png"), None))
        self.assertEqual(elements, [])


if __name__ == "__main__":
    unittest.main()

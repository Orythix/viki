"""
Performance optimization tests: low_resource_mode boot.

Verifies:
- VIKIController.low_resource_mode reflects env / settings,
- heavy modules (vision_skill, browser_skill, computer_use_skill, …) are
  NOT imported during boot when LazySkillProxy is in use.

This is a *fast* smoke test: it monkey-patches sys.modules so importing the
controller doesn't drag the optional packages along.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

from viki.core.orchestrator import VIKIController
from viki.v2.config import reset_config

HEAVY_MODULES = (
    "viki.skills.builtins.vision_skill",
    "viki.skills.builtins.browser_skill",
    "viki.skills.builtins.computer_use_skill",
    "viki.skills.builtins.whisper_skill",
    "viki.skills.builtins.pdf_skill",
    "viki.skills.builtins.image_gen_skill",
    "viki.skills.builtins.short_video_skill",
    "viki.skills.builtins.spreadsheet_skill",
    "viki.skills.builtins.presentation_skill",
    "viki.skills.builtins.data_analysis_skill",
    "viki.skills.builtins.plan_edit_skill",
)


class TestLowResourceBoot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.settings_path = os.path.join(base, "config", "settings.yaml")
        cls.soul_path = os.path.join(base, "config", "soul.yaml")

    def setUp(self):
        self._td = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        os.environ["VIKI_DATA_DIR"] = self._td.name
        os.environ["VIKI_LOW_RESOURCE"] = "1"
        for mod in HEAVY_MODULES:
            sys.modules.pop(mod, None)

    def tearDown(self):
        try:
            os.environ.pop("VIKI_LOW_RESOURCE", None)
            if hasattr(self, "controller") and self.controller is not None:
                if hasattr(self.controller, "close"):
                    try:
                        self.controller.close()
                    except Exception:
                        pass
                import asyncio

                try:
                    asyncio.run(self.controller.shutdown())
                except Exception:
                    pass
        finally:
            try:
                self._td.cleanup()
            except Exception:
                pass
            # Restore VIKI_DATA_DIR and reset config singleton
            os.environ.pop("VIKI_DATA_DIR", None)
            reset_config()

    def test_low_resource_flag_propagates(self):
        self.controller = VIKIController(self.settings_path, self.soul_path)
        self.assertTrue(self.controller.low_resource_mode)

    def test_heavy_skills_registered_but_not_imported(self):
        self.controller = VIKIController(self.settings_path, self.soul_path)
        registered = set(self.controller.skill_registry.list_skills())
        for skill_name in ("look_at_screen", "browser", "computer_use", "whisper", "pdf"):
            self.assertIn(skill_name, registered, f"{skill_name} should be registered")
        for mod in HEAVY_MODULES:
            self.assertNotIn(
                mod,
                sys.modules,
                f"{mod} should NOT be imported at boot under low_resource_mode",
            )


if __name__ == "__main__":
    unittest.main()

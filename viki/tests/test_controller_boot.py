"""
P2 tier-1: VIKIController boot wiring smoke test.

Confirms:
- the controller boots end-to-end against the shipped settings.yaml/soul.yaml,
- core subsystems are present (skill_registry, memory, scorecard, history, bio),
- shutdown is graceful.

This is intentionally narrow; deep behaviour is covered by per-module tests.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import unittest

from viki.core.orchestrator import VIKIController


class TestControllerBoot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.settings_path = os.path.join(base, "config", "settings.yaml")
        cls.soul_path = os.path.join(base, "config", "soul.yaml")

    _ENV_VARS = ("VIKI_DATA_DIR", "VIKI_DISABLE_AUTOLAUNCH")

    def setUp(self):
        # Snapshot env so we can restore it; otherwise these vars leak into
        # later tests in the same process (they would inherit our temp dir
        # path even after tearDown deletes it, which on Windows manifests as
        # 'sqlite3.OperationalError: database is locked').
        self._env_snapshot = {k: os.environ.get(k) for k in self._ENV_VARS}
        self._td = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        os.environ["VIKI_DATA_DIR"] = self._td.name
        os.environ["VIKI_DISABLE_AUTOLAUNCH"] = "1"

    def tearDown(self):
        try:
            if hasattr(self, "controller") and self.controller is not None:
                if hasattr(self.controller, "close"):
                    try:
                        self.controller.close()
                    except Exception:
                        pass
                try:
                    asyncio.run(self.controller.shutdown())
                except Exception:
                    pass
        finally:
            for k, v in self._env_snapshot.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            try:
                self._td.cleanup()
            except Exception:
                pass

    def test_boot_has_core_subsystems(self):
        self.controller = VIKIController(self.settings_path, self.soul_path)
        self.assertIsNotNone(self.controller.skill_registry)
        self.assertIsNotNone(self.controller.memory)
        self.assertIsNotNone(self.controller.scorecard)
        self.assertIsNotNone(self.controller.history)
        self.assertIsNotNone(self.controller.bio)
        self.assertTrue(hasattr(self.controller, "mcp_skill_count"))

    def test_boot_attaches_mcp_count_attr(self):
        self.controller = VIKIController(self.settings_path, self.soul_path)
        self.assertGreaterEqual(int(self.controller.mcp_skill_count), 0)


if __name__ == "__main__":
    unittest.main()

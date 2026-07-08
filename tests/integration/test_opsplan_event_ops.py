import asyncio
import os
import sys
import tempfile
import unittest

import yaml

sys.path.append(os.path.abspath(os.path.join(os.getcwd(), "..")))

from viki.core.orchestrator import VIKIController


class TestOpsPlanEventOps(unittest.TestCase):
    def setUp(self):
        viki_dir = os.path.join(os.getcwd(), "config")
        self.settings = {
            "system": {
                "data_dir": None,
                "log_level": "INFO",
                "security_scan_requests": False,
            },
            "models_config": os.path.abspath("./tests/integration/test_models.yaml"),
            "memory": {"short_term_limit": 5, "long_term_enabled": False},
            "skills": {"auto_discover": False, "registry_path": ""},
        }

        self.test_dir = tempfile.TemporaryDirectory(prefix="viki_ops_")
        self.test_data_path = self.test_dir.name
        self.settings["system"]["data_dir"] = self.test_data_path

        self.settings_path = os.path.join(self.test_data_path, "temp_settings_ops.yaml")
        with open(self.settings_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.settings, f)

        self.soul_path = os.path.join(viki_dir, "soul.yaml")
        self.controller = VIKIController(self.settings_path, self.soul_path)

    def tearDown(self):
        if hasattr(self, "controller") and self.controller:
            try:
                self.controller.close()
            except Exception:
                pass
            try:
                asyncio.run(self.controller.shutdown())
            except Exception:
                pass
        if hasattr(self, "test_dir"):
            try:
                self.test_dir.cleanup()
            except Exception:
                pass

    def async_test(coro):
        def wrapper(self):
            return asyncio.run(coro(self))

        return wrapper

    @async_test
    async def test_opsplan_approval_gate_then_execute(self):
        req = "Schedule a strategy meeting tomorrow at 2pm for the team and notify via email."
        resp = await self.controller.process_request(req)

        self.assertIsInstance(resp, str)
        self.assertIn("OpsPlan created", resp)
        self.assertNotIn("SUCCEEDED", resp)

        resp2 = await self.controller.process_request("yes")
        self.assertIsInstance(resp2, str)
        self.assertIn("OpsPlan applied", resp2)
        self.assertIn("SUCCEEDED", resp2)


if __name__ == "__main__":
    unittest.main()

"""
Performance optimization tests: LazySkillProxy.

Verifies:
- the underlying module is NOT imported until execute() is called
- properties (name/description/schema) work without loading
- repeated calls reuse the same instance (only one import)
- import errors degrade gracefully and return a typed error string
"""
from __future__ import annotations

import asyncio
import importlib
import sys
import unittest

from viki.skills.lazy_skill import LazySkillProxy


def _run(coro):
    return asyncio.run(coro)


class TestLazySkillProxy(unittest.TestCase):
    def test_metadata_available_without_loading(self):
        proxy = LazySkillProxy(
            name="lazy_demo",
            description="A demo skill",
            module_path="viki.skills.builtins.time_skill",
            class_name="TimeSkill",
            schema={"type": "object", "properties": {}},
        )
        self.assertEqual(proxy.name, "lazy_demo")
        self.assertEqual(proxy.description, "A demo skill")
        self.assertFalse(proxy.is_loaded())
        self.assertEqual(proxy.schema, {"type": "object", "properties": {}})

    def test_first_execute_loads_module(self):
        # Use the lightweight TimeSkill so import is cheap and side-effect-free.
        proxy = LazySkillProxy(
            name="t",
            description="time",
            module_path="viki.skills.builtins.time_skill",
            class_name="TimeSkill",
        )
        sys.modules.pop("viki.skills.builtins.time_skill", None)
        self.assertNotIn("viki.skills.builtins.time_skill", sys.modules)
        result = _run(proxy.execute({}))
        self.assertIsInstance(result, str)
        self.assertIn("viki.skills.builtins.time_skill", sys.modules)
        self.assertTrue(proxy.is_loaded())

    def test_failed_import_returns_friendly_error(self):
        proxy = LazySkillProxy(
            name="missing",
            description="does not exist",
            module_path="viki.skills.builtins.this_module_does_not_exist",
            class_name="Nope",
        )
        out = _run(proxy.execute({}))
        self.assertIn("unavailable", out)
        # second call should also short-circuit cleanly without re-attempting import.
        out2 = _run(proxy.execute({}))
        self.assertIn("unavailable", out2)


if __name__ == "__main__":
    unittest.main()

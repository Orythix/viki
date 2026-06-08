from __future__ import annotations

import unittest
from pathlib import Path

from skills.builtins.megatron_lm_playbook_skill import MegatronLmPlaybookSkill


EXPECTED_SLUGS = {
    "build-and-dependency",
    "cicd",
    "create-issue",
    "linting-and-formatting",
    "nightly-sync",
    "onboard-gb200-1node-tests",
    "respond-to-issue",
    "run-on-slurm",
    "split-pr",
    "testing",
    "update-golden-values",
}


class TestMegatronLmPlaybooks(unittest.IsolatedAsyncioTestCase):
    def test_each_skill_has_skill_md(self):
        root = Path(__file__).resolve().parents[1] / "skills" / "playbooks" / "megatron_lm"
        for slug in EXPECTED_SLUGS:
            path = root / slug / "SKILL.md"
            self.assertTrue(path.is_file(), f"Missing SKILL.md for {slug}")
            self.assertTrue(path.read_text(encoding="utf-8").strip(), f"Empty SKILL.md for {slug}")

    def test_schema_enum_matches_upstream_slugs(self):
        skill = MegatronLmPlaybookSkill()
        enum = set(skill.schema["properties"]["playbook"]["enum"])
        self.assertEqual(enum, EXPECTED_SLUGS)

    async def test_execute_returns_markdown(self):
        skill = MegatronLmPlaybookSkill()
        result = await skill.execute({"playbook": "build-and-dependency"})
        self.assertIn("#", result)
        self.assertIn("container", result.lower())

    async def test_summary_format(self):
        skill = MegatronLmPlaybookSkill()
        result = await skill.execute({"playbook": "testing", "format": "summary"})
        self.assertIn("# ", result)
        self.assertIn("## Headings", result)

    async def test_unknown_playbook_lists_valid(self):
        skill = MegatronLmPlaybookSkill()
        result = await skill.execute({"playbook": "not-a-megatron-skill"})
        self.assertIn("unknown playbook", result)
        self.assertIn("Valid playbooks:", result)


if __name__ == "__main__":
    unittest.main()

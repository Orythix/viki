from __future__ import annotations

import unittest
from pathlib import Path

from viki.skills.builtins.engineering_playbook_skill import EngineeringPlaybookSkill

EXPECTED_ENGINEERING = {
    "idea_refine",
    "spec_driven_development",
    "planning_and_task_breakdown",
    "incremental_implementation",
    "test_driven_development",
    "context_engineering",
    "source_driven_development",
    "frontend_ui_engineering",
    "api_and_interface_design",
    "browser_testing_with_devtools",
    "debugging_and_error_recovery",
    "code_review_and_quality",
    "code_simplification",
    "security_and_hardening",
    "performance_optimization",
    "git_workflow_and_versioning",
    "ci_cd_and_automation",
    "deprecation_and_migration",
    "documentation_and_adrs",
    "shipping_and_launch",
}
SECOND_WAVE_ENGINEERING = {
    "refactoring_and_restructuring",
    "dependency_and_package_management",
    "observability_and_monitoring",
    "database_and_schema_design",
    "caching_and_data_locality",
    "distributed_systems_patterns",
    "error_handling_and_resilience",
    "structured_logging_and_diagnostics",
    "concurrency_and_async_patterns",
    "cli_and_developer_tooling",
    "configuration_and_secrets",
    "type_safety_and_static_analysis",
    "release_engineering_and_versioning",
    "infrastructure_as_code",
    "container_and_orchestration",
    "data_engineering_and_etl",
    "llm_and_prompt_engineering",
    "agent_and_tool_use_patterns",
    "real_time_and_event_driven",
    "cryptography_and_key_management",
}
EXPECTED_REFERENCES = {
    "testing_patterns",
    "security_checklist",
    "performance_checklist",
    "accessibility_checklist",
}
EXPECTED_PERSONAS = {"code_reviewer", "test_engineer", "security_auditor"}
EXPECTED_ALL = (
    EXPECTED_ENGINEERING | SECOND_WAVE_ENGINEERING | EXPECTED_REFERENCES | EXPECTED_PERSONAS
)


class TestEngineeringPlaybooks(unittest.IsolatedAsyncioTestCase):
    def test_all_playbooks_exist_and_non_empty(self):
        root = Path(__file__).resolve().parents[1] / "src" / "viki" / "skills" / "playbooks"
        for slug in EXPECTED_ALL:
            matches = list(root.rglob(f"{slug}.md"))
            self.assertTrue(matches, f"Missing playbook file for slug: {slug}")
            content = matches[0].read_text(encoding="utf-8").strip()
            self.assertTrue(content, f"Empty playbook file for slug: {slug}")

    def test_schema_enum_contains_expected_slugs(self):
        skill = EngineeringPlaybookSkill()
        enum = set(skill.schema["properties"]["playbook"]["enum"])
        self.assertTrue(EXPECTED_ALL.issubset(enum))

    def test_second_wave_playbooks_have_required_structure(self):
        root = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "viki"
            / "skills"
            / "playbooks"
            / "engineering"
        )
        required_sections = (
            "## Overview",
            "## When to Use",
            "## Process",
            "## Rationalizations",
            "## Red Flags",
            "## Verification",
        )
        for slug in SECOND_WAVE_ENGINEERING:
            path = root / f"{slug}.md"
            self.assertTrue(path.exists(), f"Missing second-wave playbook: {slug}")
            content = path.read_text(encoding="utf-8")
            self.assertTrue(content.strip(), f"Empty second-wave playbook: {slug}")
            self.assertTrue(content.startswith("# "), f"Playbook missing H1: {slug}")
            for section in required_sections:
                self.assertIn(section, content, f"Missing section {section} in {slug}")

    def test_schema_enum_contains_second_wave_slugs(self):
        skill = EngineeringPlaybookSkill()
        enum = set(skill.schema["properties"]["playbook"]["enum"])
        for slug in SECOND_WAVE_ENGINEERING:
            self.assertIn(slug, enum)

    async def test_execute_returns_markdown_with_h1(self):
        skill = EngineeringPlaybookSkill()
        result = await skill.execute({"playbook": "spec_driven_development"})
        self.assertIn("#", result)
        self.assertIn("Spec", result)

    async def test_summary_format_includes_h1_and_headings_list(self):
        skill = EngineeringPlaybookSkill()
        result = await skill.execute({"playbook": "spec_driven_development", "format": "summary"})
        self.assertIn("# ", result)
        self.assertIn("## Headings", result)
        self.assertIn("- ", result)

    async def test_section_process_returns_process_section(self):
        skill = EngineeringPlaybookSkill()
        result = await skill.execute(
            {"playbook": "incremental_implementation", "section": "Process"}
        )
        self.assertNotIn("section 'Process' not found", result)
        self.assertTrue(
            "checklist" in result.lower()
            or "cycle" in result.lower()
            or "process" in result.lower()
        )

    async def test_invalid_playbook_returns_error_with_valid_list(self):
        skill = EngineeringPlaybookSkill()
        result = await skill.execute({"playbook": "not_a_real_playbook"})
        self.assertIn("unknown playbook", result)
        self.assertIn("Valid playbooks:", result)

    async def test_execute_second_wave_playbooks(self):
        skill = EngineeringPlaybookSkill()
        first = await skill.execute({"playbook": "observability_and_monitoring"})
        second = await skill.execute({"playbook": "refactoring_and_restructuring"})
        self.assertIn("# Observability and Monitoring", first)
        self.assertIn("## Process", first)
        self.assertIn("# Refactoring and Restructuring", second)
        self.assertIn("## Verification", second)


if __name__ == "__main__":
    unittest.main()

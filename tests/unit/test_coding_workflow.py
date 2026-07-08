from __future__ import annotations

import unittest

from viki.skills.builtins.coding_workflow_skill import CodingWorkflowSkill

EXPECTED_PHASE_PLAYBOOKS = {
    "spec": ["idea_refine", "spec_driven_development", "dependency_and_package_management"],
    "plan": ["planning_and_task_breakdown", "spec_driven_development", "infrastructure_as_code"],
    "build": [
        "incremental_implementation",
        "test_driven_development",
        "context_engineering",
        "source_driven_development",
        "api_and_interface_design",
        "frontend_ui_engineering",
        "refactoring_and_restructuring",
        "error_handling_and_resilience",
        "concurrency_and_async_patterns",
        "type_safety_and_static_analysis",
        "database_and_schema_design",
        "caching_and_data_locality",
        "distributed_systems_patterns",
        "cli_and_developer_tooling",
        "configuration_and_secrets",
        "real_time_and_event_driven",
        "cryptography_and_key_management",
        "llm_and_prompt_engineering",
        "agent_and_tool_use_patterns",
        "data_engineering_and_etl",
    ],
    "test": [
        "test_driven_development",
        "browser_testing_with_devtools",
        "debugging_and_error_recovery",
        "observability_and_monitoring",
    ],
    "review": [
        "code_review_and_quality",
        "security_and_hardening",
        "performance_optimization",
        "structured_logging_and_diagnostics",
        "dependency_and_package_management",
    ],
    "simplify": ["code_simplification", "code_review_and_quality", "refactoring_and_restructuring"],
    "ship": [
        "git_workflow_and_versioning",
        "ci_cd_and_automation",
        "deprecation_and_migration",
        "documentation_and_adrs",
        "shipping_and_launch",
        "release_engineering_and_versioning",
        "container_and_orchestration",
        "infrastructure_as_code",
        "observability_and_monitoring",
    ],
}

PHASE_NEW_EXPECTED = {
    "spec": {"dependency_and_package_management"},
    "plan": {"infrastructure_as_code"},
    "build": {
        "refactoring_and_restructuring",
        "error_handling_and_resilience",
        "concurrency_and_async_patterns",
        "type_safety_and_static_analysis",
        "database_and_schema_design",
        "caching_and_data_locality",
        "distributed_systems_patterns",
        "cli_and_developer_tooling",
        "configuration_and_secrets",
        "real_time_and_event_driven",
        "cryptography_and_key_management",
        "llm_and_prompt_engineering",
        "agent_and_tool_use_patterns",
        "data_engineering_and_etl",
    },
    "test": {"observability_and_monitoring"},
    "review": {"structured_logging_and_diagnostics", "dependency_and_package_management"},
    "simplify": {"refactoring_and_restructuring"},
    "ship": {
        "release_engineering_and_versioning",
        "container_and_orchestration",
        "infrastructure_as_code",
        "observability_and_monitoring",
    },
}


class TestCodingWorkflowSkill(unittest.IsolatedAsyncioTestCase):
    async def test_all_phases_return_playbook_stack_and_checklist(self):
        skill = CodingWorkflowSkill()
        for phase in EXPECTED_PHASE_PLAYBOOKS:
            result = await skill.execute({"phase": phase, "task": "Add search filtering"})
            self.assertTrue(result.strip())
            self.assertIn("## Playbook Stack", result)
            self.assertIn("## Checklist", result)

    async def test_each_phase_references_expected_playbooks(self):
        skill = CodingWorkflowSkill()
        for phase, playbooks in EXPECTED_PHASE_PLAYBOOKS.items():
            result = await skill.execute({"phase": phase, "task": "Improve API reliability"})
            for playbook in playbooks:
                self.assertIn(f"`{playbook}`", result)

    async def test_each_phase_includes_new_second_wave_playbook(self):
        skill = CodingWorkflowSkill()
        for phase, expected in PHASE_NEW_EXPECTED.items():
            result = await skill.execute({"phase": phase, "task": "Improve API reliability"})
            self.assertTrue(
                any(f"`{slug}`" in result for slug in expected),
                f"Phase {phase} did not include a mapped second-wave playbook",
            )

    async def test_invalid_phase_returns_clear_error(self):
        skill = CodingWorkflowSkill()
        result = await skill.execute({"phase": "unknown", "task": "Do work"})
        self.assertIn("invalid phase", result)
        self.assertIn("Valid phases:", result)


if __name__ == "__main__":
    unittest.main()

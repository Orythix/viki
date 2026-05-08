from __future__ import annotations

from typing import Any, Dict, List

from viki.skills.base import BaseSkill
from viki.skills.builtins.engineering_playbook_skill import EngineeringPlaybookSkill


class CodingWorkflowSkill(BaseSkill):
    PHASE_PLAYBOOKS: Dict[str, List[str]] = {
        "spec": [
            "idea_refine",
            "spec_driven_development",
            "dependency_and_package_management",
        ],
        "plan": [
            "planning_and_task_breakdown",
            "spec_driven_development",
            "infrastructure_as_code",
        ],
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
        "simplify": [
            "code_simplification",
            "code_review_and_quality",
            "refactoring_and_restructuring",
        ],
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
    NEXT_PHASE: Dict[str, str] = {
        "spec": "plan",
        "plan": "build",
        "build": "test",
        "test": "review",
        "review": "simplify",
        "simplify": "ship",
        "ship": "complete",
    }

    def __init__(self) -> None:
        self._playbooks = EngineeringPlaybookSkill()

    @property
    def name(self) -> str:
        return "coding_workflow"

    @property
    def description(self) -> str:
        return (
            "Runs a structured coding lifecycle phase (spec/plan/build/test/review/simplify/ship), "
            "returning the playbook stack and a step-by-step checklist for that phase."
        )

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "phase": {
                    "type": "string",
                    "enum": list(self.PHASE_PLAYBOOKS.keys()),
                    "description": "Lifecycle phase to run.",
                },
                "task": {"type": "string", "description": "User's coding task for this phase."},
                "context": {"type": "string", "description": "Optional paths/decisions context."},
            },
            "required": ["phase", "task"],
        }

    async def _h1_for(self, playbook: str) -> str:
        markdown = await self._playbooks.execute({"playbook": playbook, "format": "markdown"})
        for line in markdown.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
        return playbook.replace("_", " ").title()

    async def execute(self, params: Dict[str, Any]) -> str:
        phase = str(params.get("phase") or "").strip().lower()
        task = str(params.get("task") or "").strip()
        context = str(params.get("context") or "").strip()

        if phase not in self.PHASE_PLAYBOOKS:
            valid = ", ".join(self.PHASE_PLAYBOOKS.keys())
            return f"coding_workflow: invalid phase '{phase}'. Valid phases: {valid}"
        if not task:
            return "coding_workflow: 'task' is required."

        stack = self.PHASE_PLAYBOOKS[phase]
        primary = stack[0]

        playbook_lines: List[str] = []
        for slug in stack:
            title = await self._h1_for(slug)
            playbook_lines.append(f"- `{slug}`: {title}")

        checklist_sections: List[str] = []
        for heading in ("Process", "Verification", "Red Flags"):
            section = await self._playbooks.execute({"playbook": primary, "section": heading, "format": "markdown"})
            if section.startswith("engineering_playbook: section"):
                continue
            checklist_sections.append(section)

        checklist_body = "\n\n".join(checklist_sections).strip() or "No checklist sections found."
        next_step = self.NEXT_PHASE.get(phase, "complete")
        stack_text = "\n".join(playbook_lines)

        context_block = f"\n\n## Context\n{context}" if context else ""
        return (
            f"# Coding Workflow: {phase} — {task}\n\n"
            "## Playbook Stack\n"
            f"{stack_text}\n\n"
            "## Checklist\n"
            f"{checklist_body}\n\n"
            f"## Next Step\nMove to `{next_step}`."
            f"{context_block}\n"
        )

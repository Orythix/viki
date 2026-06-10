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
        "audit": [
            "security_and_hardening",
            "security-scan",
            "security-review",
        ],
        "redteam": [
            "REDTEAM",
            "security-bounty-hunter",
            "security_and_hardening",
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
        "review": "audit",
        "audit": "simplify",
        "redteam": "audit",
        "simplify": "ship",
        "ship": "complete",
    }

    def __init__(self, controller=None) -> None:
        self._controller = controller
        self._playbooks = EngineeringPlaybookSkill()

    @property
    def name(self) -> str:
        return "coding_workflow"

    @property
    def description(self) -> str:
        return (
            "Professional Coding Lifecycle Orchestrator. Manages the state of a coding task.\n"
            "- run(phase='build', task='...'): Get the playbook and checklist for a specific phase.\n"
            "- start(goal='...', project='...'): Initialize a new coding mission.\n"
            "- update(phase='...'): Progress to the next lifecycle phase.\n"
            "- finish(success=True): Finalize and close the current mission."
        )

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["run", "start", "update", "finish"],
                    "default": "run",
                    "description": "Lifecycle action to perform.",
                },
                "phase": {
                    "type": "string",
                    "enum": list(self.PHASE_PLAYBOOKS.keys()),
                    "description": "Lifecycle phase (required for 'run').",
                },
                "task": {"type": "string", "description": "Goal/Task description."},
                "context": {"type": "string", "description": "Optional paths/decisions context."},
                "success": {"type": "boolean", "default": True, "description": "Used with 'finish' action."}
            },
            "required": ["action"]
        }

    async def execute(self, params: Dict[str, Any]) -> str:
        action = str(params.get("action") or "run").strip().lower()
        world = self._controller.world if self._controller else None

        if action == "start":
            goal = params.get("task") or params.get("goal")
            if not goal: return "Error: 'task' is required to start a mission."
            if world: world.start_mission(goal, params.get("project"))
            return f"Mission Started: {goal}"

        elif action == "update":
            phase = params.get("phase")
            if not phase: return "Error: 'phase' is required for update."
            if world: world.update_mission_phase(phase)
            return f"Mission Phase Updated to: {phase}"

        elif action == "finish":
            success = params.get("success", True)
            summary = params.get("summary", "")
            if world: world.finish_mission(summary, success)
            return f"Mission Finished (Success={success})"

        elif action == "resume":
            if not world or not world.state.active_goal:
                return "Error: No active mission found in WorldModel to resume."
            # Reroute to 'run' with current world state
            return await self.execute({
                "action": "run",
                "phase": world.state.current_phase.lower(),
                "task": world.state.active_goal
            })

        elif action == "run":
            phase = str(params.get("phase") or "").strip().lower()
            task = str(params.get("task") or "").strip()
            context = str(params.get("context") or "").strip()

            if not phase:
                # If we have an active mission, use its phase
                if world and world.state.active_goal:
                    phase = world.state.current_phase.lower()
                    if not task: task = world.state.active_goal
                else:
                    return "Error: 'phase' is required when no active mission exists."

            if phase not in self.PHASE_PLAYBOOKS:
                valid = ", ".join(self.PHASE_PLAYBOOKS.keys())
                return f"coding_workflow: invalid phase '{phase}'. Valid phases: {valid}"

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
            
            # Auto-update world phase if running through phases
            if world and world.state.active_goal:
                world.update_mission_phase(phase)

            return (
                f"# Coding Workflow: {phase.upper()} — {task}\n\n"
                "## Playbook Stack\n"
                f"{stack_text}\n\n"
                "## Checklist\n"
                f"{checklist_body}\n\n"
                f"## Next Step\nMove to `{next_step}`."
                f"{context_block}\n"
            )
        
        return f"Error: Unknown action '{action}'"

    async def _h1_for(self, slug: str) -> str:
        """Helper to extract the H1 title of a playbook by its slug."""
        markdown = self._playbooks._load_playbook(slug)
        if not markdown:
            return "Untitled Playbook"
        for line in markdown.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
        return "Untitled Playbook"


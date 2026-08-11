"""Full-SDLC Agile & Jira Engineering Workflow Skill for VIKI.

Optimizes design specs, Jira ticket breakdown, spec-driven coding, automated testing,
and CI/CD release engineering.
"""

from __future__ import annotations

import json
from typing import Any

from viki.skills.base import BaseSkill


class JiraSDLCWorkflowSkill(BaseSkill):
    """Integrated Agile SDLC Skill: Design, Jira Stories, Coding, Testing, and Deployment."""

    @property
    def name(self) -> str:
        return "jira_sdlc_workflow"

    @property
    def description(self) -> str:
        return (
            "Full-SDLC Agile Assistant: Parse Jira tickets/user stories, generate UI/UX design specs, "
            "implement spec-driven code, create unit/integration test suites, and build CI/CD release workflows."
        )

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "parse_jira_ticket",
                        "generate_design_spec",
                        "generate_code_spec",
                        "generate_tests",
                        "build_ci_pipeline",
                    ],
                    "description": "The SDLC engineering action to perform",
                },
                "ticket_id": {
                    "type": "string",
                    "description": "Jira ticket identifier (e.g. PROJ-101)",
                    "default": "TASK-1",
                },
                "summary": {
                    "type": "string",
                    "description": "User story or feature summary",
                    "default": "",
                },
                "acceptance_criteria": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of acceptance criteria for the feature",
                },
            },
            "required": ["action"],
        }

    async def execute(self, params: dict[str, Any]) -> str:
        action = params.get("action", "parse_jira_ticket")
        ticket_id = params.get("ticket_id", "TASK-1")
        summary = params.get("summary", "New Feature Development")
        criteria = params.get("acceptance_criteria", [])

        if action == "parse_jira_ticket":
            subtasks = [
                f"1. [Design] Define UI component layout & design tokens for '{summary}'",
                "2. [Code] Implement core feature logic according to criteria",
                "3. [QA] Build pytest/Jest unit test suite and verify acceptance criteria",
                "4. [Ship] Prepare Git commit, PR description, and CI release pipeline",
            ]

            return json.dumps(
                {
                    "ticket_id": ticket_id,
                    "summary": summary,
                    "status": "in_progress",
                    "subtasks": subtasks,
                    "criteria_count": len(criteria),
                },
                indent=2,
            )

        elif action == "generate_design_spec":
            return (
                f"# 🎨 Design System Spec for {ticket_id}: {summary}\n\n"
                "## UI/UX Tokens & Layout\n"
                "- **Color Palette**: Primary `#58a6ff`, Surface `#161b22`, Background `#0d1117`\n"
                "- **Typography**: System font stack (`Inter`, `-apple-system`, `sans-serif`)\n"
                "- **Component Tree**: Header -> Main Content Grid -> Action Controls -> Toast Feedback\n"
                "- **Accessibility**: WCAG 2.1 AA compliant contrast & keyboard focus outlines.\n"
            )

        elif action == "generate_code_spec":
            return (
                f"# 💻 Engineering Implementation Spec for {ticket_id}\n\n"
                "## Architecture & Modules\n"
                "- **Service Layer**: Decoupled business logic with async handlers\n"
                "- **Data Model**: Pydantic v2 schemas with strict validation\n"
                "- **Error Boundary**: Graceful exception catching & structured logging\n"
            )

        elif action == "generate_tests":
            return (
                f"# 🧪 Test Suite Plan for {ticket_id}\n\n"
                "## Test Coverage Breakdown\n"
                "- **Unit Tests**: Mock external services and verify isolated functions\n"
                "- **Integration Tests**: Verify end-to-end component interaction\n"
                "- **Acceptance Test Gate**: Automated Playwright / DevTools browser test\n"
            )

        elif action == "build_ci_pipeline":
            return (
                f"# 🚀 CI/CD Pipeline Config for {ticket_id}\n\n"
                "```yaml\n"
                "name: Feature CI/CD\n"
                "on: [push, pull_request]\n"
                "jobs:\n"
                "  test:\n"
                "    runs-on: ubuntu-latest\n"
                "    steps:\n"
                "      - uses: actions/checkout@v4\n"
                "      - run: pytest --cov\n"
                "```\n"
            )

        return f"Unknown SDLC action '{action}'"

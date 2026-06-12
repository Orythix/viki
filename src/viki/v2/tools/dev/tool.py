"""DevTool — repository analysis, code review, debug."""

from __future__ import annotations

from ...core.permission_manager import PermissionTier
from ..base import BaseTool, ToolResult
from .providers import DevProvider


class DevTool(BaseTool):
    name = "dev"
    description = "Analyze repositories, review code, debug, detect tech stack."
    capabilities = [
        "analyze_repo",
        "analyze_file",
        "detect_stack",
        "suggest_improvements",
    ]
    permission_tier = PermissionTier.SAFE
    examples = [
        "Analyze my project structure",
        "Review src/main.py for issues",
        "What frameworks does this repo use?",
        "Suggest improvements for this codebase",
    ]
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["analyze_repo", "analyze_file", "detect_stack", "suggest_improvements"],
                "description": "Development action",
            },
            "path": {"type": "string", "description": "File or directory path"},
        },
        "required": ["action", "path"],
    }

    def __init__(self, provider: DevProvider | None = None):
        self.provider = provider or DevProvider()

    async def execute(self, params: dict, provider=None) -> ToolResult:
        p = provider or self.provider
        action = params.get("action")
        path = params.get("path")

        try:
            if action == "analyze_repo":
                profile = await p.analyze_repository(path)
                return ToolResult(success=True, data=vars(profile))

            elif action == "analyze_file":
                analysis = await p.analyze_python_file(path)
                return ToolResult(success=True, data=analysis)

            elif action == "detect_stack":
                profile = await p.analyze_repository(path)
                return ToolResult(
                    success=True,
                    data={
                        "languages": profile.languages,
                        "frameworks": profile.frameworks,
                        "build_system": profile.build_system,
                        "test_framework": profile.test_framework,
                        "has_docker": profile.has_docker,
                        "has_ci": profile.has_ci,
                    },
                )

            elif action == "suggest_improvements":
                profile = await p.analyze_repository(path)
                suggestions = []
                if not profile.test_framework:
                    suggestions.append("Add test framework configuration")
                if not profile.has_ci:
                    suggestions.append("Add CI/CD pipeline")
                if not profile.has_docker:
                    suggestions.append("Add Dockerfile for containerization")
                if not profile.entry_points:
                    suggestions.append("Define clear entry points")
                return ToolResult(success=True, data={"suggestions": suggestions})

            else:
                return ToolResult(
                    success=False,
                    error=f"Unknown action: {action}",
                    error_type="invalid_parameters",
                )

        except Exception as e:
            return ToolResult(success=False, error=str(e), error_type="execution_failed")

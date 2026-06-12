"""GitTool — git operations."""

from __future__ import annotations

from ...core.permission_manager import PermissionTier
from ..base import BaseTool, ToolResult
from .providers import GitProvider


class GitTool(BaseTool):
    name = "git"
    description = "Git repository operations: status, log, branches, diff, commit, push, pull."
    capabilities = [
        "status",
        "log",
        "branches",
        "diff",
        "add",
        "commit",
        "push",
        "pull",
        "remote",
    ]
    permission_tier = PermissionTier.ELEVATED  # read is safe, write needs elevated
    examples = [
        "Show git status",
        "Show recent commits",
        "List all branches",
        "Show diff of current changes",
        "Commit all changes with message",
        "Push to origin",
    ]
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "status",
                    "log",
                    "branches",
                    "diff",
                    "add",
                    "commit",
                    "push",
                    "pull",
                    "remote",
                ],
                "description": "Git action to perform",
            },
            "path": {"type": "string", "description": "Repository path (default: cwd)"},
            "message": {"type": "string", "description": "Commit message"},
            "target": {
                "type": "string",
                "description": "Target for diff/push/pull (branch, commit, etc.)",
            },
            "files": {"type": "string", "description": "Files for add (default: .)"},
        },
        "required": ["action"],
    }

    def __init__(self, provider: GitProvider | None = None):
        self.provider = provider or GitProvider()

    async def get_permission_tier(self, params: dict) -> PermissionTier:
        """Dynamic permission tier based on action."""
        action = params.get("action", "")
        if action in ("status", "log", "branches", "diff", "remote"):
            return PermissionTier.SAFE
        elif action in ("add", "commit", "push", "pull"):
            return PermissionTier.ELEVATED
        return PermissionTier.ADMIN

    async def execute(self, params: dict, provider=None) -> ToolResult:
        p = provider or self.provider
        action = params.get("action")
        path = params.get("path")

        try:
            if action == "status":
                data = await p.status(path)
                return ToolResult(success=True, data=data)

            elif action == "log":
                limit = params.get("target", 10)
                if isinstance(limit, str) and limit.isdigit():
                    limit = int(limit)
                data = await p.log(limit, path)
                return ToolResult(success=True, data={"commits": data})

            elif action == "branches":
                data = await p.branches(path)
                return ToolResult(success=True, data=data)

            elif action == "diff":
                target = params.get("target", "HEAD")
                data = await p.diff(target, path)
                return ToolResult(success=True, data={"diff": data})

            elif action == "add":
                files = params.get("files", ".")
                await p.add(files, path)
                return ToolResult(success=True, data={"added": files})

            elif action == "commit":
                message = params.get("message")
                if not message:
                    return ToolResult(
                        success=False,
                        error="Commit message required",
                        error_type="invalid_parameters",
                    )
                out = await p.commit(message, path)
                return ToolResult(success=True, data={"message": message, "output": out})

            elif action == "push":
                remote = params.get("target", "origin")
                branch = params.get("files")
                out = await p.push(remote, branch, path)
                return ToolResult(
                    success=True, data={"remote": remote, "branch": branch, "output": out}
                )

            elif action == "pull":
                remote = params.get("target", "origin")
                branch = params.get("files")
                out = await p.pull(remote, branch, path)
                return ToolResult(
                    success=True, data={"remote": remote, "branch": branch, "output": out}
                )

            elif action == "remote":
                remote = params.get("target", "origin")
                url = await p.remote_url(remote, path)
                return ToolResult(success=True, data={"remote": remote, "url": url})

            else:
                return ToolResult(
                    success=False,
                    error=f"Unknown action: {action}",
                    error_type="invalid_parameters",
                )

        except Exception as e:
            return ToolResult(success=False, error=str(e), error_type="execution_failed")

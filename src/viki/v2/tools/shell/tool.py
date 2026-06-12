"""ShellTool — execute commands with output capture."""

from __future__ import annotations

from ...core.permission_manager import PermissionTier
from ..base import BaseTool, ToolResult
from .providers import LocalShellProvider, ShellProvider


class ShellTool(BaseTool):
    name = "shell"
    description = "Executes terminal commands with output capture and session management."
    capabilities = [
        "run_command",
        "stream_command",
    ]
    permission_tier = PermissionTier.ADMIN
    examples = [
        "Run 'dir' in my project folder",
        "Execute pytest tests/",
        "Show disk usage",
        "List all environment variables",
        "Run a long-running build command",
    ]
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["run", "stream"],
                "description": "Run normally or stream output",
            },
            "command": {"type": "string", "description": "Command to execute"},
            "workdir": {"type": "string", "description": "Working directory"},
            "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 60},
        },
        "required": ["action", "command"],
    }

    def __init__(self, provider: ShellProvider | None = None):
        self.provider = provider or LocalShellProvider()

    async def execute(self, params: dict, provider=None) -> ToolResult:
        p = provider or self.provider
        action = params.get("action")
        command = params.get("command")
        workdir = params.get("workdir")
        timeout = params.get("timeout", 60)

        try:
            if action == "run":
                result = await p.run(command, workdir, timeout)
                return ToolResult(
                    success=result.returncode == 0,
                    data={
                        "command": command,
                        "returncode": result.returncode,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                    },
                    error=result.stderr if result.returncode != 0 else None,
                    error_type="execution_failed" if result.returncode != 0 else None,
                )

            elif action == "stream":
                # For non-streaming execution, just run it
                result = await p.run(command, workdir, timeout)
                return ToolResult(
                    success=result.returncode == 0,
                    data={
                        "command": command,
                        "returncode": result.returncode,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                    },
                    error=result.stderr if result.returncode != 0 else None,
                    error_type="execution_failed" if result.returncode != 0 else None,
                )

            else:
                return ToolResult(
                    success=False,
                    error=f"Unknown action: {action}",
                    error_type="invalid_parameters",
                )

        except Exception as e:
            return ToolResult(success=False, error=str(e), error_type="execution_failed")

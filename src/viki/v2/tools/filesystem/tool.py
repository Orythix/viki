"""FileSystemTool — read, write, search, analyze files."""

from __future__ import annotations

from ...core.permission_manager import PermissionTier
from ..base import BaseTool, ToolResult
from .providers import FSProvider, LocalFSProvider


class FileSystemTool(BaseTool):
    name = "filesystem"
    description = "Reads, writes, searches, and manages files within allowed boundaries."
    capabilities = [
        "read_file",
        "write_file",
        "list_dir",
        "search_files",
        "create_dir",
        "delete_file",
        "copy_file",
        "move_file",
        "file_info",
    ]
    permission_tier = PermissionTier.SAFE  # Dynamic based on action
    examples = [
        "Read src/main.py",
        "Create a new file at config/settings.json",
        "Search for files containing 'api_key'",
        "List files in my project directory",
        "Delete the logs folder",
    ]
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "read",
                    "write",
                    "list",
                    "search",
                    "mkdir",
                    "delete",
                    "copy",
                    "move",
                    "info",
                ],
                "description": "Filesystem action to perform",
            },
            "path": {"type": "string", "description": "File or directory path"},
            "content": {"type": "string", "description": "Content for write action"},
            "pattern": {"type": "string", "description": "Glob pattern for search"},
            "destination": {"type": "string", "description": "Destination for copy/move"},
        },
        "required": ["action", "path"],
    }

    def __init__(self, provider: FSProvider | None = None):
        self.provider = provider or LocalFSProvider()

    async def get_permission_tier(self, params: dict) -> PermissionTier:
        """Dynamic permission tier based on action."""
        action = params.get("action", "")
        if action in ("read", "list", "search", "info"):
            return PermissionTier.SAFE
        elif action in ("mkdir", "copy", "move"):
            return PermissionTier.ELEVATED
        else:  # write, delete
            return PermissionTier.ADMIN

    async def execute(self, params: dict, provider=None) -> ToolResult:
        p = provider or self.provider
        action = params.get("action")
        path = params.get("path")

        try:
            if action == "read":
                data = await p.read_file(path)
                return ToolResult(success=True, data={"path": path, "content": data})

            elif action == "write":
                content = params.get("content", "")
                await p.write_file(path, content)
                return ToolResult(success=True, data={"path": path, "bytes": len(content)})

            elif action == "list":
                items = await p.list_dir(path)
                return ToolResult(
                    success=True,
                    data={"path": path, "items": [vars(i) for i in items]},
                )

            elif action == "search":
                pattern = params.get("pattern", "*")
                files = await p.search_files(path, pattern)
                return ToolResult(
                    success=True, data={"root": path, "pattern": pattern, "files": files}
                )

            elif action == "mkdir":
                await p.mkdir(path)
                return ToolResult(success=True, data={"path": path, "created": True})

            elif action == "delete":
                await p.remove(path, recursive=True)
                return ToolResult(success=True, data={"path": path, "deleted": True})

            elif action == "copy":
                dst = params.get("destination")
                await p.copy(path, dst)
                return ToolResult(success=True, data={"source": path, "destination": dst})

            elif action == "move":
                dst = params.get("destination")
                await p.move(path, dst)
                return ToolResult(success=True, data={"source": path, "destination": dst})

            elif action == "info":
                info = await p.get_file_info(path)
                if info:
                    return ToolResult(success=True, data=vars(info))
                return ToolResult(success=False, error="File not found", error_type="not_found")

            else:
                return ToolResult(
                    success=False,
                    error=f"Unknown action: {action}",
                    error_type="invalid_parameters",
                )

        except Exception as e:
            return ToolResult(success=False, error=str(e), error_type="execution_failed")

"""SystemTool — OS and hardware information."""

from __future__ import annotations

from ...core.permission_manager import PermissionTier
from ...providers.base import SystemProvider
from ..base import BaseTool, ToolResult


class SystemTool(BaseTool):
    name = "system"
    description = "Retrieves operating system and hardware information."
    capabilities = [
        "get_os_info",
        "get_hardware_info",
        "get_cpu_info",
        "get_ram_info",
        "get_disk_info",
        "get_network_info",
        "get_running_processes",
        "get_installed_software",
    ]
    permission_tier = PermissionTier.SAFE
    examples = [
        "What OS am I running?",
        "Show me my hardware specs",
        "How much RAM do I have?",
        "List running processes",
        "What software is installed?",
    ]
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "enum": [
                    "os",
                    "hardware",
                    "cpu",
                    "ram",
                    "disk",
                    "network",
                    "processes",
                    "software",
                    "all",
                ],
                "description": "What system information to retrieve",
            }
        },
        "required": ["query"],
    }

    def __init__(self, provider: SystemProvider | None = None):
        self.provider = provider

    async def execute(self, params: dict, provider=None) -> ToolResult:
        p = provider or self.provider
        if not p:
            return ToolResult(success=False, error="No system provider available")

        query = params.get("query", "all")
        try:
            if query == "os":
                data = await p.get_os_info()
            elif query == "hardware":
                data = await p.get_hardware_info()
            elif query == "cpu":
                data = await p.get_cpu_info()
            elif query == "ram":
                data = await p.get_ram_info()
            elif query == "disk":
                data = await p.get_disk_info()
            elif query == "network":
                data = await p.get_network_info()
            elif query == "processes":
                data = await p.get_running_processes()
            elif query == "software":
                data = await p.get_installed_software()
            else:
                data = {
                    "os": await p.get_os_info(),
                    "hardware": await p.get_hardware_info(),
                    "ram": await p.get_ram_info(),
                    "disk": await p.get_disk_info(),
                }
            return ToolResult(success=True, data=data)
        except Exception as e:
            return ToolResult(success=False, error=str(e), error_type="execution_failed")

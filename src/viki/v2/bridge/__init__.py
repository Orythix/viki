"""V2ToolBridge — wraps V2 ToolRegistry as a V1 skill for gradual migration."""

from __future__ import annotations

import json
import os
from typing import Any

from viki.skills.base import BaseSkill
from viki.v2.tools.registry import ToolRegistry

_V2_MODE = os.environ.get("VIKI_V2_MODE", "0").lower() in ("1", "true", "yes", "on")


def is_v2_mode() -> bool:
    """Check if V2 mode is enabled."""
    return _V2_MODE


def set_v2_mode(enabled: bool):
    global _V2_MODE
    _V2_MODE = enabled


class V2ToolBridge(BaseSkill):
    """
    Bridges V2 ToolRegistry into V1 skill system.

    When VIKI_V2_MODE=1, V2 tools appear alongside V1 skills.
    The LLM can call either system transparently.
    """

    def __init__(self, registry: ToolRegistry | None = None):
        self._registry = registry or ToolRegistry()
        self._provider = None
        self._perm_manager = None

    # --- BaseSkill interface ---

    @property
    def name(self) -> str:
        return "v2_tools"

    @property
    def description(self) -> str:
        return "Unified V2 tool system: filesystem, shell, git, database, dev, system, network."

    @property
    def instructions(self) -> str:
        return self.description

    @property
    def schema(self) -> dict:
        """Dynamic schema generated from registered V2 tools."""
        return {
            "type": "object",
            "properties": {
                "tools": {"type": "array", "items": {"type": "string"}},
            },
        }

    @property
    def safety_tier(self) -> str:
        return "medium"

    def get_tool_definition(self) -> dict:
        tools_defs = [tool.get_tool_definition() for tool in self._registry._tools.values()]
        tool_count = len(tools_defs)
        desc = self.description
        if tool_count:
            desc += f"\n{tool_count} tools available"
        return {
            "type": "function",
            "function": {
                "name": "v2_tools",
                "description": desc,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tool_name": {
                            "type": "string",
                            "description": "V2 tool to execute",
                            "enum": list(self._registry._tools.keys()),
                        },
                        "tool_params": {
                            "type": "object",
                            "description": "Parameters for the selected tool",
                        },
                    },
                    "required": ["tool_name", "tool_params"],
                },
            },
        }

    async def execute(self, params: dict[str, Any]) -> str:
        """Execute a V2 tool via the bridge."""
        tool_name = params.get("tool_name")
        tool_params = params.get("tool_params", {})

        if not tool_name:
            return "Error: 'tool_name' is required"

        provider = self._provider
        result = await self._registry.execute(tool_name, tool_params, provider=provider)

        if result.success:
            return json.dumps(result.data, indent=2, default=str)
        return f"Error: {result.error}"

    # --- V2 integration methods ---

    def set_provider(self, provider):
        """Set the system provider for V2 tools."""
        self._provider = provider

    def set_permission_manager(self, perm_manager):
        """Set the V2 permission manager."""
        self._perm_manager = perm_manager

    def register_all(self, *tools):
        """Register multiple V2 tools at once."""
        for tool in tools:
            self._registry.register(tool)

    def list_tools(self) -> list[str]:
        return self._registry.list_tools()


def create_v2_bridge(provider=None) -> V2ToolBridge:
    """Factory: creates and wires a fully-populated V2ToolBridge."""
    from viki.v2.providers import create_provider
    from viki.v2.tools.database.tool import DatabaseTool
    from viki.v2.tools.dev.tool import DevTool
    from viki.v2.tools.filesystem.tool import FileSystemTool
    from viki.v2.tools.git.tool import GitTool
    from viki.v2.tools.network.tool import NetworkTool
    from viki.v2.tools.shell.tool import ShellTool
    from viki.v2.tools.system.tool import SystemTool

    p = provider or create_provider()
    bridge = V2ToolBridge()
    bridge.set_provider(p)
    bridge.register_all(
        SystemTool(provider=p),
        NetworkTool(provider=p),
        FileSystemTool(),
        ShellTool(),
        GitTool(),
        DatabaseTool(),
        DevTool(),
    )

    # Register MCP tools if available
    try:
        from viki.v2.tools.mcp import register_mcp_tools

        mcp_count = register_mcp_tools(bridge._registry)
        if mcp_count:
            pass
    except Exception:
        pass

    return bridge

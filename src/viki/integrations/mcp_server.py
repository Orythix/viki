"""
MCP server mode — expose VIKI's skills and memory to external agents/IDEs.

Implements the Model Context Protocol (MCP) as a server so other agents,
IDEs (VS Code, Cursor, etc.), and automation tools can:
  - List and invoke VIKI skills
  - Query VIKI's knowledge graph and memory
  - Subscribe to events

Uses stdio transport by default (fits IDE integrations).
Optional SSE transport for remote access.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from viki.config.logger import viki_logger

try:
    from mcp.server import Server as MCPServer
    from mcp.server.stdio import stdio_server
    from mcp.types import (
        CallToolRequest,
        CallToolResult,
        ListToolsRequest,
        ListToolsResult,
        ReadResourceRequest,
        ReadResourceResult,
        TextContent,
        Tool,
    )

    _MCP_AVAILABLE = True
except ImportError:
    _MCP_AVAILABLE = False


class VikiMCPServer:
    """
    MCP server that exposes VIKI capabilities.

    Requires the ``mcp`` package (``pip install mcp``).
    Attach to a running VIKIController or provide standalone access to
    the skill registry and learning module.
    """

    def __init__(
        self,
        skill_registry: Any | None = None,
        learning_module: Any | None = None,
        mission_control: Any | None = None,
        server_name: str = "viki-mcp",
    ):
        self._skill_registry = skill_registry
        self._learning_module = learning_module
        self._mission_control = mission_control
        self._server_name = server_name
        self._server: Any = None

    async def start_stdio(self) -> None:
        """Start the MCP server over stdio transport (for IDE integration)."""
        if not _MCP_AVAILABLE:
            viki_logger.error(
                "MCP server requires the 'mcp' package. Install with: pip install mcp"
            )
            return

        self._server = MCPServer(self._server_name)

        self._server.register_handler("list_tools")(self._handle_list_tools)
        self._server.register_handler("call_tool")(self._handle_call_tool)

        async with stdio_server() as (read_stream, write_stream):
            await self._server.run(
                read_stream, write_stream, self._server.create_initialization_options()
            )

    async def _handle_list_tools(self, request: ListToolsRequest) -> ListToolsResult:
        """Return all registered skills as MCP tools."""
        tools: list[Tool] = []
        if self._skill_registry is None:
            return ListToolsResult(tools=[])

        for name in self._skill_registry.list_skills():
            skill = self._skill_registry.get_skill(name)
            if skill is None:
                continue
            tools.append(
                Tool(
                    name=name,
                    description=skill.description,
                    inputSchema=skill.schema
                    or {"type": "object", "properties": {}, "required": []},
                )
            )
        return ListToolsResult(tools=tools)

    async def _handle_call_tool(self, request: CallToolRequest) -> CallToolResult:
        """Execute a skill via MCP."""
        if self._skill_registry is None:
            return CallToolResult(
                content=[TextContent(type="text", text="Skill registry not available")],
                isError=True,
            )

        skill = self._skill_registry.get_skill(request.name)
        if skill is None:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Skill '{request.name}' not found")],
                isError=True,
            )

        try:
            result = await skill.execute(request.arguments or {})
            return CallToolResult(
                content=[TextContent(type="text", text=str(result))],
            )
        except Exception as e:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Error executing {request.name}: {e}")],
                isError=True,
            )

    async def _handle_read_resource(self, request: ReadResourceRequest) -> ReadResourceResult:
        """Read a VIKI resource (memory, knowledge graph, etc.)."""
        uri = request.uri
        if uri.startswith("viki://memory/"):
            query = uri.removeprefix("viki://memory/")
            if self._learning_module:
                lessons = self._learning_module.get_lessons(query=query, limit=10)
                return ReadResourceResult(
                    contents=[TextContent(type="text", text=json.dumps(lessons, indent=2))]
                )
        elif uri.startswith("viki://knowledge/"):
            query = uri.removeprefix("viki://knowledge/")
            if self._learning_module:
                lessons = self._learning_module.get_relevant_lessons(query, limit=10)
                return ReadResourceResult(
                    contents=[TextContent(type="text", text="\n".join(lessons))]
                )
        elif uri.startswith("viki://missions/"):
            if self._mission_control:
                missions = list(self._mission_control.active_missions.values())
                return ReadResourceResult(
                    contents=[
                        TextContent(
                            type="text", text=json.dumps([m.to_dict() for m in missions], indent=2)
                        )
                    ]
                )

        return ReadResourceResult(
            contents=[TextContent(type="text", text=f"Resource not found: {uri}")],
            isError=True,
        )


async def run_mcp_server_stdio(
    skill_registry: Any | None = None,
    learning_module: Any | None = None,
    mission_control: Any | None = None,
) -> None:
    """Convenience function to start a stdio-based MCP server."""
    server = VikiMCPServer(
        skill_registry=skill_registry,
        learning_module=learning_module,
        mission_control=mission_control,
    )
    await server.start_stdio()


def main() -> None:
    """Entry point for standalone MCP server."""
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_mcp_server_stdio())


if __name__ == "__main__":
    main()

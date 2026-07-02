"""MCPTool — wraps a single MCP tool as a V2 BaseTool."""

from __future__ import annotations

import asyncio
from typing import Any

from ..base import BaseTool, ToolResult
from ..registry import ToolRegistry
from .client import V2MCPClient
from .config import load_mcp_config

_PERMISSION_MAP = {
    "safe": "SAFE",
    "medium": "ELEVATED",
    "destructive": "ADMIN",
}


class MCPTool(BaseTool):
    """Wraps a single MCP tool as a V2 tool.

    The ``client`` and ``server`` fields are set after construction by the
    factory / registry — the tool itself is lightweight.
    """

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict,
        server: str,
        tool_name: str,
        safety_tier: str = "medium",
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self._server = server
        self._tool_name = tool_name
        self._client: V2MCPClient | None = None

        tier_name = _PERMISSION_MAP.get(safety_tier, "ELEVATED")
        from ...core.permission_manager import PermissionTier

        self.permission_tier = PermissionTier[tier_name]
        self.capabilities = ["mcp", server]
        self.examples = [f"Call MCP tool '{tool_name}' via server '{server}'"]

    def bind_client(self, client: V2MCPClient):
        self._client = client

    async def execute(self, params: dict, provider=None) -> ToolResult:
        if self._client is None:
            return ToolResult(success=False, error="MCPTool not bound to a client")
        try:
            result = await self._client.call_tool(self._server, self._tool_name, params)
            content = _extract_content(result)
            return ToolResult(success=True, data=content)
        except Exception as e:
            return ToolResult(success=False, error=str(e), error_type="mcp_error")

    def get_tool_definition(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": f"[MCP/{self._server}] {self.description}",
                "parameters": self.parameters,
            },
        }


def _extract_content(result: Any) -> Any:
    """Extract text content from an MCP SDK tool result."""
    try:
        if hasattr(result, "content") and result.content:
            texts = []
            for part in result.content:
                if hasattr(part, "text") and part.text:
                    texts.append(part.text)
            if texts:
                return "\n".join(texts)
        return str(result)
    except Exception:
        return str(result)


async def register_mcp_tools_async(
    registry: ToolRegistry,
    config_path: str | None = None,
    client: V2MCPClient | None = None,
) -> int:
    """Discover MCP servers from config and register their tools (async).

    Returns the number of tools registered.
    """
    specs = load_mcp_config(config_path)
    if not specs:
        return 0

    if client is None:
        client = V2MCPClient()

    if not client.is_available:
        return 0

    count = 0
    for spec in specs:
        ok = await client.connect(spec)
        if not ok:
            continue
        for meta in client.list_available_tools().values():
            if meta["server"] != spec.name:
                continue
            tool_name = meta["tool_name"].replace("-", "_").replace(".", "_")
            qualified = f"mcp_{spec.name}_{tool_name}"

            tool = MCPTool(
                name=qualified,
                description=meta["description"],
                parameters=meta["input_schema"],
                server=spec.name,
                tool_name=meta["tool_name"],
                safety_tier=meta["safety_tier"],
            )
            tool.bind_client(client)
            registry.register(tool)
            count += 1

    return count


def register_mcp_tools(
    registry: ToolRegistry,
    config_path: str | None = None,
    client: V2MCPClient | None = None,
) -> int:
    """Discover MCP servers from config and register their tools (sync wrapper).

    ⚠ Use ``register_mcp_tools_async`` when already inside an async context.

    Returns the number of tools registered.
    """
    try:
        # Safe — no running event loop
        return asyncio.run(register_mcp_tools_async(registry, config_path, client))
    except RuntimeError as e:
        if "cannot be called from a running event loop" in str(e):
            raise RuntimeError(
                "register_mcp_tools() called from within an async context. "
                "Use register_mcp_tools_async() instead."
            ) from e
        raise

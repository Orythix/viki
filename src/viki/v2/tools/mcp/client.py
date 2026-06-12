"""V2 MCP client — manages connections to MCP servers."""

from __future__ import annotations

import os
from contextlib import AsyncExitStack
from typing import Any

from viki.config.logger import viki_logger

from .config import MCPServerSpec


class V2MCPClient:
    """Manages MCP server connections and tool calls.

    Lazily imports the ``mcp`` SDK — if it is not installed, all operations
    gracefully degrade (return empty tools, log a warning).
    """

    def __init__(self):
        self._sessions: dict[str, Any] = {}
        self._exit_stacks: dict[str, AsyncExitStack] = {}
        self._tools: dict[str, dict[str, Any]] = {}
        self._sdk_available = False
        self._import_sdk()

    # ------------------------------------------------------------------
    # SDK availability
    # ------------------------------------------------------------------

    def _import_sdk(self) -> None:
        try:
            import mcp  # noqa: F401

            self._sdk_available = True
        except ImportError:
            self._sdk_available = False
            viki_logger.info("V2 MCP: ``mcp`` SDK not installed — MCP servers disabled")

    @property
    def is_available(self) -> bool:
        return self._sdk_available

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    async def connect(self, spec: MCPServerSpec) -> bool:
        """Connect to a single MCP server and ingest its tools.

        Returns ``True`` on success.
        """
        if not self._sdk_available:
            return False

        transport = spec.transport.replace("-", "_")

        connect_fn = getattr(self, f"_connect_{transport}", None)
        if connect_fn is None:
            viki_logger.warning(
                "V2 MCP: unknown transport '%s' for server '%s'", spec.transport, spec.name
            )
            return False

        try:
            await connect_fn(spec)
            return True
        except Exception as e:
            viki_logger.warning("V2 MCP: failed to connect to '%s': %s", spec.name, e)
            return False

    async def _connect_stdio(self, spec: MCPServerSpec) -> None:
        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        if not spec.command:
            raise ValueError(f"stdio server '{spec.name}' has no 'command'")

        params = StdioServerParameters(
            command=spec.command,
            args=list(spec.args),
            env={**os.environ, **spec.env} if spec.env else None,
        )

        stack = AsyncExitStack()
        transport = await stack.enter_async_context(stdio_client(params))
        session = await stack.enter_async_context(ClientSession(*transport))
        await session.initialize()

        self._exit_stacks[spec.name] = stack
        self._sessions[spec.name] = session
        await self._ingest_tools(spec, session)

    async def _connect_http(self, spec: MCPServerSpec) -> None:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        if not spec.url:
            raise ValueError(f"http server '{spec.name}' has no 'url'")

        import httpx

        stack = AsyncExitStack()
        http_client = httpx.AsyncClient(
            headers=spec.headers or None,
            timeout=httpx.Timeout(spec.timeout, read=max(spec.timeout * 2, 120)),
        )
        await stack.enter_async_context(http_client)
        transport = await stack.enter_async_context(streamable_http_client(spec.url, http_client))
        session = await stack.enter_async_context(ClientSession(*transport))
        await session.initialize()

        self._exit_stacks[spec.name] = stack
        self._sessions[spec.name] = session
        await self._ingest_tools(spec, session)

    async def _connect_sse(self, spec: MCPServerSpec) -> None:
        from mcp import ClientSession
        from mcp.client.sse import sse_client

        if not spec.url:
            raise ValueError(f"sse server '{spec.name}' has no 'url'")

        stack = AsyncExitStack()
        transport = await stack.enter_async_context(
            sse_client(
                url=spec.url,
                headers=spec.headers or None,
                timeout=max(spec.timeout * 3, 60),
            )
        )
        session = await stack.enter_async_context(ClientSession(*transport))
        await session.initialize()

        self._exit_stacks[spec.name] = stack
        self._sessions[spec.name] = session
        await self._ingest_tools(spec, session)

    # ------------------------------------------------------------------
    # Tool ingestion
    # ------------------------------------------------------------------

    async def _ingest_tools(self, spec: MCPServerSpec, session: Any) -> None:
        resp = await session.list_tools()
        for tool in resp.tools:
            key = f"{spec.name}::{tool.name}"
            self._tools[key] = {
                "server": spec.name,
                "tool_name": tool.name,
                "description": tool.description or "",
                "input_schema": tool.inputSchema or {},
                "safety_tier": spec.safety_tier,
                "requires_confirmation": spec.requires_confirmation,
            }
            viki_logger.debug("V2 MCP: registered tool '%s' from '%s'", tool.name, spec.name)

    # ------------------------------------------------------------------
    # Tool listing & calling
    # ------------------------------------------------------------------

    def list_available_tools(self) -> dict[str, dict[str, Any]]:
        """Return all ingested MCP tools keyed by ``server::tool_name``."""
        return dict(self._tools)

    async def call_tool(self, server: str, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Call a tool on a connected MCP server."""
        session = self._sessions.get(server)
        if session is None:
            raise ConnectionError(f"Not connected to MCP server '{server}'")
        result = await session.call_tool(tool_name, arguments)
        return result

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def disconnect_all(self) -> None:
        """Disconnect from all MCP servers."""
        for name, stack in self._exit_stacks.items():
            try:
                await stack.aclose()
            except Exception as e:
                viki_logger.debug("V2 MCP: error closing '%s': %s", name, e)
        self._sessions.clear()
        self._exit_stacks.clear()
        self._tools.clear()

    async def disconnect(self, server: str) -> None:
        """Disconnect from a single server."""
        stack = self._exit_stacks.pop(server, None)
        if stack:
            try:
                await stack.aclose()
            except Exception as e:
                viki_logger.debug("V2 MCP: error closing '%s': %s", server, e)
        self._sessions.pop(server, None)
        self._tools = {k: v for k, v in self._tools.items() if v["server"] != server}

"""
Phase 3: Model Context Protocol (MCP) client.

Allows VIKI to consume MCP servers (Cursor, Claude Code, Figma, Supabase, etc.)
as if their tools were native VIKI skills. Each MCP tool is wrapped in a tiny
`MCPSkillProxy` that proxies `execute(params)` calls over the MCP transport.

Configuration lives in `viki/config/mcp_servers.yaml`:

    servers:
      figma:
        command: ["npx", "-y", "@figma/mcp-server"]
        env:
          FIGMA_TOKEN: ${FIGMA_TOKEN}
      supabase:
        command: ["npx", "-y", "@supabase/mcp-server"]

This module deliberately depends on `mcp` lazily: a missing dependency disables
MCP support but never breaks the controller.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from viki.config.logger import viki_logger
from viki.skills.base import BaseSkill


@dataclass
class MCPServerSpec:
    name: str
    command: List[str]
    env: Dict[str, str] = field(default_factory=dict)
    args: List[str] = field(default_factory=list)


class MCPClient:
    """
    Lightweight async wrapper around the official `mcp` SDK if installed.

    Falls back to "no-op" stubs so the rest of VIKI keeps working in
    environments where MCP isn't installed.
    """

    def __init__(self):
        self._sessions: Dict[str, Any] = {}
        self._tools: Dict[str, Dict[str, Any]] = {}  # full tool key -> tool dict
        self._lock = asyncio.Lock()
        self._sdk_available = self._import_sdk()

    @staticmethod
    def _import_sdk() -> bool:
        try:
            import mcp  # noqa: F401
            return True
        except ImportError:
            viki_logger.debug("MCP SDK not installed; MCP integration is no-op.")
            return False

    async def connect(self, spec: MCPServerSpec) -> bool:
        if not self._sdk_available:
            return False
        try:
            from mcp import ClientSession  # type: ignore
            from mcp.client.stdio import StdioServerParameters, stdio_client  # type: ignore
        except Exception as e:
            viki_logger.debug("MCP SDK incompatible: %s", e)
            return False

        try:
            params = StdioServerParameters(
                command=spec.command[0],
                args=list(spec.command[1:]) + spec.args,
                env={**os.environ, **spec.env},
            )
            stdio_ctx = stdio_client(params)
            read, write = await stdio_ctx.__aenter__()
            session = ClientSession(read, write)
            await session.__aenter__()
            await session.initialize()

            tools_resp = await session.list_tools()
            self._sessions[spec.name] = {
                "session": session,
                "stdio_ctx": stdio_ctx,
                "spec": spec,
            }
            for tool in getattr(tools_resp, "tools", []) or []:
                tool_dict = {
                    "name": tool.name,
                    "description": tool.description or "",
                    "input_schema": getattr(tool, "inputSchema", {}) or {},
                }
                key = f"{spec.name}::{tool.name}"
                self._tools[key] = tool_dict
            viki_logger.info(
                "MCP: connected '%s' (%d tools).",
                spec.name,
                len([k for k in self._tools if k.startswith(f"{spec.name}::")]),
            )
            return True
        except Exception as e:
            viki_logger.warning("MCP: failed to connect '%s': %s", spec.name, e)
            return False

    async def disconnect_all(self) -> None:
        for name, entry in list(self._sessions.items()):
            try:
                await entry["session"].__aexit__(None, None, None)
                await entry["stdio_ctx"].__aexit__(None, None, None)
            except Exception as e:
                viki_logger.debug("MCP: disconnect '%s' failed: %s", name, e)
        self._sessions.clear()
        self._tools.clear()

    def list_tools(self) -> List[Dict[str, Any]]:
        out = []
        for key, tool in self._tools.items():
            server, tool_name = key.split("::", 1)
            out.append({"server": server, "tool": tool_name, **tool})
        return out

    async def call_tool(self, server: str, tool: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        entry = self._sessions.get(server)
        if entry is None:
            return {"error": f"MCP server '{server}' not connected."}
        session = entry["session"]
        try:
            resp = await session.call_tool(name=tool, arguments=arguments or {})
            payload = []
            for item in getattr(resp, "content", []) or []:
                text = getattr(item, "text", None)
                if text is not None:
                    payload.append(text)
            return {"result": "\n".join(payload), "raw_meta": getattr(resp, "meta", None)}
        except Exception as e:
            return {"error": str(e)}


class MCPSkillProxy(BaseSkill):
    """Wrap a single MCP tool as a VIKI BaseSkill so the planner can invoke it."""

    def __init__(self, client: MCPClient, server: str, tool: Dict[str, Any]):
        self._client = client
        self._server = server
        self._tool = tool

    @property
    def name(self) -> str:
        # Use a stable, namespaced name so two servers can expose tools with the same name.
        return f"mcp_{self._server}_{self._tool['name']}".replace("-", "_")

    @property
    def description(self) -> str:
        return f"[MCP/{self._server}] {self._tool.get('description', '')}".strip()

    @property
    def schema(self) -> Dict[str, Any]:
        return self._tool.get("input_schema") or {"type": "object", "properties": {}}

    @property
    def safety_tier(self) -> str:
        # MCP tools that mutate external state should be tagged via mcp_servers.yaml in a future iteration.
        return "medium"

    async def execute(self, params: Dict[str, Any]) -> str:
        result = await self._client.call_tool(self._server, self._tool["name"], params or {})
        if result.get("error"):
            return f"MCP error: {result['error']}"
        return str(result.get("result") or "")


def load_specs_from_yaml(path: str) -> List[MCPServerSpec]:
    """Read a Cursor-style MCP server config and return MCPServerSpec list."""
    import yaml

    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    servers = data.get("servers", {}) or {}
    out: List[MCPServerSpec] = []
    for name, cfg in servers.items():
        cmd = cfg.get("command")
        if isinstance(cmd, str):
            cmd = [cmd]
        elif not isinstance(cmd, list):
            continue
        env = {k: os.path.expandvars(str(v)) for k, v in (cfg.get("env") or {}).items()}
        args = cfg.get("args") or []
        out.append(MCPServerSpec(name=name, command=list(cmd), env=env, args=list(args)))
    return out


async def attach_mcp_skills(controller, mcp_config_path: Optional[str] = None) -> int:
    """
    Load MCP servers from yaml, register their tools as VIKI skills, and return
    the count of skills installed.
    """
    if not getattr(controller, "skill_registry", None):
        return 0
    cfg_path = mcp_config_path or os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "config",
        "mcp_servers.yaml",
    )
    cfg_path = os.path.abspath(cfg_path)
    specs = load_specs_from_yaml(cfg_path)
    if not specs:
        return 0
    client = MCPClient()
    if not client._sdk_available:
        return 0
    controller.mcp_client = client
    installed = 0
    for spec in specs:
        ok = await client.connect(spec)
        if not ok:
            continue
        for tool_meta in client.list_tools():
            if tool_meta["server"] != spec.name:
                continue
            proxy = MCPSkillProxy(client, spec.name, tool_meta)
            controller.skill_registry.register_skill(proxy)
            installed += 1
    return installed

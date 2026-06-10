"""
Phase 3: Model Context Protocol (MCP) client.

Allows VIKI to consume MCP servers (Cursor, Claude Code, Figma, Supabase, etc.)
as if their tools were native VIKI skills. Each MCP tool is wrapped in a tiny
`MCPSkillProxy` that proxies `execute(params)` calls over the MCP transport.

Configuration lives in `viki/config/mcp_servers.yaml`:

    servers:
      local_demo:
        transport: stdio
        command: ["npx", "-y", "@some/mcp-server"]
        env:
          TOKEN: ${TOKEN}
      remote:
        transport: http
        url: https://example.com/mcp
        headers:
          Authorization: Bearer ${MCP_TOKEN}
        timeout: 45
        safety_tier: medium
        requires_confirmation: false
        tools:
          delete_stuff:
            safety_tier: destructive
            requires_confirmation: true

Transports (Python MCP SDK):
  - stdio: spawn a subprocess (default)
  - http / streamable_http: Streamable HTTP per MCP spec
  - sse: legacy SSE MCP endpoint

This module deliberately depends on `mcp` lazily: a missing dependency disables
MCP support but never breaks the controller. Integration follows the public MCP
spec and the official Python SDK — not third-party proprietary sources.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import AsyncExitStack
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Tuple

from viki.config.logger import viki_logger
from viki.skills.base import BaseSkill


def _normalize_transport(raw: Optional[str]) -> str:
    t = (raw or "stdio").strip().lower()
    if t in ("streamable_http", "streamable-http"):
        return "http"
    return t


@dataclass
class MCPServerSpec:
    name: str
    transport: str = "stdio"
    command: List[str] = field(default_factory=list)
    url: str = ""
    env: Dict[str, str] = field(default_factory=dict)
    args: List[str] = field(default_factory=list)
    headers: Dict[str, str] = field(default_factory=dict)
    timeout_s: float = 30.0
    enabled: bool = True
    default_safety_tier: str = "medium"
    default_requires_confirmation: bool = False
    tool_policies: Dict[str, Dict[str, Any]] = field(default_factory=dict)


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
        self._server_status: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _import_sdk() -> bool:
        try:
            import mcp  # noqa: F401
            return True
        except ImportError:
            viki_logger.debug("MCP SDK not installed; MCP integration is no-op.")
            return False

    def get_server_status(self) -> List[Dict[str, Any]]:
        """Last-known connection status per server (for HTTP API / health)."""
        return [dict(v) for v in self._server_status.values()]

    def _set_status(
        self,
        spec: MCPServerSpec,
        *,
        connected: bool,
        tool_count: int = 0,
        error: Optional[str] = None,
    ) -> None:
        self._server_status[spec.name] = {
            "name": spec.name,
            "transport": spec.transport,
            "connected": connected,
            "tool_count": tool_count,
            "error": error,
        }

    async def connect(self, spec: MCPServerSpec) -> bool:
        if not self._sdk_available:
            self._set_status(spec, connected=False, error="MCP SDK not installed")
            return False
        if not spec.enabled:
            self._set_status(spec, connected=False, error="disabled in config")
            return False

        transport = _normalize_transport(spec.transport)
        spec = replace(spec, transport=transport)

        try:
            if transport == "stdio":
                ok = await self._connect_stdio(spec)
            elif transport == "http":
                ok = await self._connect_streamable_http(spec)
            elif transport == "sse":
                ok = await self._connect_sse(spec)
            else:
                viki_logger.warning("MCP: unknown transport '%s' for '%s'", transport, spec.name)
                self._set_status(spec, connected=False, error=f"unknown transport: {transport}")
                return False
            return ok
        except Exception as e:
            viki_logger.warning("MCP: failed to connect '%s': %s", spec.name, e)
            self._set_status(spec, connected=False, error=str(e))
            return False

    async def _connect_stdio(self, spec: MCPServerSpec) -> bool:
        from mcp import ClientSession  # type: ignore
        from mcp.client.stdio import StdioServerParameters, stdio_client  # type: ignore

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
        n = self._ingest_tools(spec.name, tools_resp)
        self._sessions[spec.name] = {
            "session": session,
            "stdio_ctx": stdio_ctx,
            "spec": spec,
            "transport": "stdio",
        }
        viki_logger.info("MCP: connected '%s' (stdio, %d tools).", spec.name, n)
        self._set_status(spec, connected=True, tool_count=n)
        return True

    async def _connect_streamable_http(self, spec: MCPServerSpec) -> bool:
        import httpx
        from mcp import ClientSession  # type: ignore
        from mcp.client.streamable_http import streamable_http_client  # type: ignore

        read_timeout = max(float(spec.timeout_s) * 2, 120.0)
        to = httpx.Timeout(float(spec.timeout_s), read=read_timeout)
        headers = dict(spec.headers)
        http_client = httpx.AsyncClient(headers=headers, timeout=to)
        stack = AsyncExitStack()
        await stack.enter_async_context(http_client)
        read, write = await stack.enter_async_context(
            streamable_http_client(spec.url, http_client=http_client)
        )
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        tools_resp = await session.list_tools()
        n = self._ingest_tools(spec.name, tools_resp)
        self._sessions[spec.name] = {
            "session": session,
            "stack": stack,
            "spec": spec,
            "transport": "http",
        }
        viki_logger.info("MCP: connected '%s' (http, %d tools).", spec.name, n)
        self._set_status(spec, connected=True, tool_count=n)
        return True

    async def _connect_sse(self, spec: MCPServerSpec) -> bool:
        import httpx
        from mcp import ClientSession  # type: ignore
        from mcp.client.sse import sse_client  # type: ignore

        headers = dict(spec.headers) if spec.headers else None
        sse_read = max(60.0, float(spec.timeout_s) * 3)
        stack = AsyncExitStack()
        read, write = await stack.enter_async_context(
            sse_client(
                spec.url,
                headers=headers,
                timeout=float(spec.timeout_s),
                sse_read_timeout=sse_read,
            )
        )
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        tools_resp = await session.list_tools()
        n = self._ingest_tools(spec.name, tools_resp)
        self._sessions[spec.name] = {
            "session": session,
            "stack": stack,
            "spec": spec,
            "transport": "sse",
        }
        viki_logger.info("MCP: connected '%s' (sse, %d tools).", spec.name, n)
        self._set_status(spec, connected=True, tool_count=n)
        return True

    def _ingest_tools(self, server_name: str, tools_resp: Any) -> int:
        count = 0
        for tool in getattr(tools_resp, "tools", []) or []:
            tool_dict = {
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": getattr(tool, "inputSchema", {}) or {},
            }
            key = f"{server_name}::{tool.name}"
            self._tools[key] = tool_dict
            count += 1
        return count

    async def disconnect_all(self) -> None:
        for name, entry in list(self._sessions.items()):
            try:
                if entry.get("stack") is not None:
                    await entry["stack"].aclose()
                else:
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

    def __init__(
        self,
        client: MCPClient,
        server: str,
        tool: Dict[str, Any],
        *,
        safety_tier: str = "medium",
        requires_confirmation: bool = False,
    ):
        self._client = client
        self._server = server
        self._tool = tool
        self._safety_tier = safety_tier
        self._requires_confirmation = bool(requires_confirmation)

    @property
    def name(self) -> str:
        return f"mcp_{self._server}_{self._tool['name']}".replace("-", "_")

    @property
    def description(self) -> str:
        return f"[MCP/{self._server}] {self._tool.get('description', '')}".strip()

    @property
    def schema(self) -> Dict[str, Any]:
        return self._tool.get("input_schema") or {"type": "object", "properties": {}}

    @property
    def safety_tier(self) -> str:
        return self._safety_tier

    @property
    def requires_user_confirmation(self) -> bool:
        return self._requires_confirmation

    async def execute(self, params: Dict[str, Any]) -> str:
        result = await self._client.call_tool(self._server, self._tool["name"], params or {})
        if result.get("error"):
            return f"MCP error: {result['error']}"
        return str(result.get("result") or "")


def _resolve_tool_policy(spec: MCPServerSpec, tool_name: str) -> Tuple[str, bool]:
    tier = spec.default_safety_tier or "medium"
    confirm = bool(spec.default_requires_confirmation)
    pol = spec.tool_policies.get(tool_name) or spec.tool_policies.get(tool_name.replace("_", "-"))
    if isinstance(pol, dict):
        if pol.get("safety_tier"):
            tier = str(pol["safety_tier"])
        if pol.get("requires_confirmation") is not None:
            confirm = bool(pol["requires_confirmation"])
    return tier, confirm


def load_specs_from_yaml(path: str) -> List[MCPServerSpec]:
    """Read MCP server config (stdio, http, sse) and return MCPServerSpec list."""
    import yaml

    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    servers = data.get("servers", {}) or {}
    out: List[MCPServerSpec] = []
    for name, cfg in servers.items():
        if not isinstance(cfg, dict):
            continue
        if cfg.get("enabled") is False:
            continue
        transport = _normalize_transport(cfg.get("transport"))
        cmd: List[str] = []
        if isinstance(cfg.get("command"), str):
            cmd = [cfg["command"]]
        elif isinstance(cfg.get("command"), list):
            cmd = [str(x) for x in cfg["command"]]

        url = str(cfg.get("url") or "").strip()
        if transport == "stdio":
            if not cmd:
                viki_logger.warning("MCP: skip '%s' — stdio transport requires non-empty command.", name)
                continue
        elif transport in ("http", "sse"):
            if not url:
                viki_logger.warning("MCP: skip '%s' — %s transport requires url.", name, transport)
                continue
        else:
            viki_logger.warning("MCP: skip '%s' — unknown transport '%s'.", name, transport)
            continue

        env = {k: os.path.expandvars(str(v)) for k, v in (cfg.get("env") or {}).items()}
        raw_headers = cfg.get("headers") or {}
        headers = (
            {k: os.path.expandvars(str(v)) for k, v in raw_headers.items()}
            if isinstance(raw_headers, dict)
            else {}
        )
        args = cfg.get("args") or []
        if not isinstance(args, list):
            args = []
        timeout = cfg.get("timeout")
        try:
            timeout_s = float(timeout) if timeout is not None else 30.0
        except (TypeError, ValueError):
            timeout_s = 30.0

        tier = str(cfg.get("safety_tier") or "medium")
        def_confirm = bool(cfg.get("requires_confirmation", False))
        tools_raw = cfg.get("tools") or {}
        tool_policies: Dict[str, Dict[str, Any]] = {}
        if isinstance(tools_raw, dict):
            for tname, pol in tools_raw.items():
                if isinstance(pol, dict):
                    tool_policies[str(tname)] = dict(pol)

        out.append(
            MCPServerSpec(
                name=name,
                transport=transport,
                command=cmd,
                url=url,
                env=env,
                args=[str(x) for x in args],
                headers=headers,
                timeout_s=timeout_s,
                enabled=cfg.get("enabled", True) is not False,
                default_safety_tier=tier,
                default_requires_confirmation=def_confirm,
                tool_policies=tool_policies,
            )
        )
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
    cap = getattr(controller, "capabilities", None)
    mcp_cap = cap.get("mcp_tools") if cap is not None else None
    installed = 0
    for spec in specs:
        ok = await client.connect(spec)
        if not ok:
            continue
        for tool_meta in client.list_tools():
            if tool_meta["server"] != spec.name:
                continue
            tier, req_c = _resolve_tool_policy(spec, tool_meta["tool"])
            proxy = MCPSkillProxy(
                client,
                spec.name,
                tool_meta,
                safety_tier=tier,
                requires_confirmation=req_c,
            )
            controller.skill_registry.register_skill(proxy)
            if mcp_cap is not None and proxy.name not in mcp_cap.linked_skills:
                mcp_cap.linked_skills.append(proxy.name)
            installed += 1
    return installed

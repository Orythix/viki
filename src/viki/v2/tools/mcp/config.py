"""MCP server configuration loader."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from viki.config.logger import viki_logger


@dataclass
class MCPServerSpec:
    name: str
    transport: str = "stdio"
    command: str | None = None
    args: list[str] = field(default_factory=list)
    url: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    timeout: int = 30
    safety_tier: str = "medium"
    requires_confirmation: bool = False
    tools: dict[str, dict[str, Any]] = field(default_factory=dict)


def load_mcp_config(path: str | None = None) -> list[MCPServerSpec]:
    """Load MCP server specs from a YAML config file.

    Searches in order:
      1. Explicit *path*
      2. ``config/mcp_servers.yaml`` relative to project root
      3. ``~/.config/viki/mcp_servers.yaml``
      4. ``./mcp_servers.yaml`` (CWD)
    """
    candidates: list[str] = []
    if path:
        candidates.append(path)

    project_root = Path(__file__).resolve().parents[4]
    candidates.append(str(project_root / "config" / "mcp_servers.yaml"))
    candidates.append(str(Path.home() / ".config" / "viki" / "mcp_servers.yaml"))
    candidates.append("mcp_servers.yaml")

    for p in candidates:
        resolved = Path(p)
        if resolved.is_file():
            try:
                with open(resolved, encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                servers_raw = data.get("servers", {})
                specs = [_parse_spec(name, raw) for name, raw in servers_raw.items()]
                viki_logger.info("V2 MCP: loaded %d server specs from %s", len(specs), resolved)
                return specs
            except Exception as e:
                viki_logger.warning("V2 MCP: failed to load %s: %s", resolved, e)

    viki_logger.info("V2 MCP: no config file found, no MCP servers configured")
    return []


def _parse_spec(name: str, raw: dict[str, Any]) -> MCPServerSpec:
    """Parse a single server entry from YAML."""
    env = {}
    for k, v in (raw.get("env", {}) or {}).items():
        env[k] = _expand_env_var(str(v))

    headers = {}
    for k, v in (raw.get("headers", {}) or {}).items():
        headers[k] = _expand_env_var(str(v))

    timeout = raw.get("timeout", 30)
    if not isinstance(timeout, int):
        try:
            timeout = int(timeout)
        except (ValueError, TypeError):
            timeout = 30

    return MCPServerSpec(
        name=name,
        transport=raw.get("transport", "stdio"),
        command=raw.get("command"),
        args=raw.get("args", []),
        url=raw.get("url"),
        env=env,
        headers=headers,
        timeout=max(timeout, 5),
        safety_tier=raw.get("safety_tier", "medium"),
        requires_confirmation=bool(raw.get("requires_confirmation", False)),
        tools=raw.get("tools", {}) or {},
    )


def _expand_env_var(value: str) -> str:
    """Expand ${VAR} references from the process environment."""
    import re

    def _replace(m: re.Match) -> str:
        var = m.group(1)
        return os.environ.get(var, "")

    return re.sub(r"\$\{(\w+)\}", _replace, value)

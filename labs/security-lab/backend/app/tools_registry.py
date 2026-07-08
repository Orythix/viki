"""
Permissioned tool registry — shell (allowlisted), HTTP GET to sandbox only.

Risks: shell escape, SSRF if HTTP not restricted.

Mitigations: allowlist binaries; timeout; no shell=True; validate URLs against internal host allowlist.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from typing import Any

import httpx
from security.sandbox_url import validate_http_target

from app.config import Settings

logger = logging.getLogger(__name__)


class ToolResult:
    def __init__(self, ok: bool, output: str, meta: dict[str, Any] | None = None) -> None:
        self.ok = ok
        self.output = output
        self.meta = meta or {}


class ToolRegistry:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def list_tools(self) -> list[str]:
        return ["shell_echo", "http_get_sandbox"]

    def run_shell_echo(self, argv: list[str], allowlist: set[str]) -> ToolResult:
        if not argv:
            return ToolResult(False, "no argv")
        bin_name = argv[0].lower()
        resolved = shutil.which(argv[0])
        if not resolved:
            return ToolResult(False, f"binary not found: {argv[0]}")
        base = bin_name
        if base not in allowlist:
            logger.warning("tool_shell_denied", extra={"extra_fields": {"binary": base}})
            return ToolResult(False, f"binary not in allowlist: {base}")
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=15,
                shell=False,
            )
            out = (proc.stdout or "") + (proc.stderr or "")
            return ToolResult(proc.returncode == 0, out.strip()[:8000], {"code": proc.returncode})
        except subprocess.TimeoutExpired:
            return ToolResult(False, "timeout")
        except OSError as e:
            return ToolResult(False, str(e))

    async def http_get_sandbox(self, url: str, allowed_hosts: list[str]) -> ToolResult:
        try:
            ok, reason = validate_http_target(url, allowed_hosts)
            if not ok:
                logger.warning("tool_http_denied_host", extra={"extra_fields": {"reason": reason}})
                return ToolResult(False, reason)
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(url)
                body = r.text[:8000]
                return ToolResult(True, body, {"status": r.status_code})
        except Exception as e:
            return ToolResult(False, str(e))

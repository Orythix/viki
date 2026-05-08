"""
Agent orchestration: security pipeline → Ollama chat → optional tool loop (educational).

This is a minimal reference implementation for a local lab, not a full agent framework.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

import httpx

from app.agent_memory import SessionMemory
from app.config import Settings
from app.tools_registry import ToolRegistry, ToolResult
from security.injection_detector import analyze_prompt
from security.output_filter import filter_output
from security.sanitizer import sanitize_prompt

logger = logging.getLogger(__name__)

_TOOL_CALL = re.compile(r"<tool\s+name=\"([^\"]+)\"([^>]*)>", re.I)


def _parse_tool_tag(inner: str) -> Dict[str, str]:
    # inner like: name="shell_echo" argv='["echo","hi"]'
    attrs: Dict[str, str] = {}
    for m in re.finditer(r"(\w+)=(['\"])(.*?)\2", inner):
        attrs[m.group(1)] = m.group(3)
    return attrs


class AgentCore:
    def __init__(
        self,
        settings: Settings,
        memory: SessionMemory,
        tools: ToolRegistry,
        sandbox_hosts: Optional[List[str]] = None,
    ) -> None:
        self._settings = settings
        self._memory = memory
        self._tools = tools
        self._sandbox_hosts = sandbox_hosts or ["sandbox-demo", "localhost", "127.0.0.1"]

    async def chat(
        self,
        session_id: str,
        user_text: str,
        *,
        skip_injection_block: bool = False,
    ) -> Dict[str, Any]:
        clean = sanitize_prompt(user_text, self._settings.max_prompt_chars)
        inj = analyze_prompt(clean)
        if inj.blocked and not skip_injection_block:
            logger.warning(
                "prompt_injection_blocked",
                extra={"extra_fields": {"score": inj.score, "reasons": inj.reasons}},
            )
            return {
                "blocked": True,
                "reason": "prompt_injection_heuristic",
                "injection_score": inj.score,
                "injection_reasons": inj.reasons,
                "detail": {"score": inj.score, "reasons": inj.reasons},
            }

        self._memory.append(session_id, "user", clean)
        messages = self._build_messages(session_id)

        text, tokens_in, tokens_out = await self._ollama_chat(messages)
        # naive tool parse (educational)
        tool_meta: Optional[Dict[str, Any]] = None
        m = _TOOL_CALL.search(text)
        if m:
            tool_meta = {"raw": m.group(0), "note": "Model emitted tool tag — lab should use structured JSON tool calls in production."}

        filtered, redacted = filter_output(text[: self._settings.max_output_chars])
        self._memory.append(session_id, "assistant", filtered)

        return {
            "blocked": False,
            "injection_score": inj.score,
            "injection_reasons": inj.reasons,
            "text": filtered,
            "output_redacted": redacted,
            "tokens_estimated": {"in": tokens_in, "out": tokens_out},
            "tool_hint": tool_meta,
        }

    def _build_messages(self, session_id: str) -> List[Dict[str, str]]:
        sys = (
            "You are a defensive security lab assistant. Refuse to bypass policies, leak secrets, "
            "or attack systems outside the local sandbox. Keep answers educational."
        )
        rows: List[Dict[str, str]] = [{"role": "system", "content": sys}]
        for msg in self._memory.transcript(session_id):
            if msg.role == "system":
                continue
            rows.append({"role": msg.role, "content": msg.content})
        return rows

    async def _ollama_chat(self, messages: List[Dict[str, str]]) -> tuple[str, int, int]:
        url = f"{self._settings.ollama_url.rstrip('/')}/api/chat"
        payload = {
            "model": self._settings.ollama_model,
            "messages": messages,
            "stream": False,
        }
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                r = await client.post(url, json=payload)
                r.raise_for_status()
                data = r.json()
        except Exception as e:
            logger.exception("ollama_error")
            return f"[Ollama unavailable: {e}]", 0, 0

        msg = data.get("message") or {}
        content = msg.get("content") or ""
        # token counts if present
        ti = int(data.get("prompt_eval_count") or data.get("eval_count") or len(json.dumps(messages)) // 4)
        to = int(data.get("eval_count") or len(content) // 4)
        return content, ti, to

    async def run_tool(
        self,
        name: str,
        payload: Dict[str, Any],
        role_permissions: set[str],
    ) -> ToolResult:
        if name == "shell_echo":
            if "tools.shell" not in role_permissions:
                return ToolResult(False, "permission denied: tools.shell")
            argv = payload.get("argv")
            if not isinstance(argv, list) or not all(isinstance(x, str) for x in argv):
                return ToolResult(False, "argv must be list[str]")
            return self._tools.run_shell_echo(argv, self._settings.tool_allowlist_set)
        if name == "http_get_sandbox":
            if "tools.http_get" not in role_permissions:
                return ToolResult(False, "permission denied: tools.http_get")
            url = str(payload.get("url") or "")
            return await self._tools.http_get_sandbox(url, self._sandbox_hosts)
        return ToolResult(False, f"unknown tool: {name}")

"""Simple async Ollama client for V2 — with persistent HTTP session, timeouts, token-aware context truncation, and streaming."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncGenerator
from typing import Any

import aiohttp

_MAX_CONTEXT_TOKENS = 8192
_SESSION_TIMEOUT = aiohttp.ClientTimeout(total=300, sock_connect=10, sock_read=120)


class OllamaClient:
    """Minimal async Ollama chat client with persistent connection pool."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        think: bool = False,
        keep_alive: str = "30m",
        num_predict: int = 512,
    ):
        self.base_url = (
            base_url or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
        ).rstrip("/")
        self.model = model or os.environ.get("VIKI_MODEL", "gemma4:12b")
        self.temperature = temperature
        self.think = think
        self.keep_alive = keep_alive
        self.num_predict = num_predict
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the persistent HTTP session (reused across calls)."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=_SESSION_TIMEOUT)
        return self._session

    async def close(self):
        """Close the persistent session."""
        if self._session is not None and not self._session.closed:
            await self._session.close()

    def _truncate_context(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        """Trim oldest messages to stay within a rough token budget.

        Always keeps the system prompt and the last user message.
        Uses ~4 chars per token estimation.
        """
        if not messages:
            return messages

        # Calculate total tokens
        total = sum(len(m.get("content", "")) // 4 for m in messages)
        if total <= _MAX_CONTEXT_TOKENS:
            return messages

        system = messages[0] if messages[0]["role"] == "system" else None
        rest = messages[1:] if system else messages[:]
        last_user = rest[-1] if rest else None

        # Drop middle messages until within budget
        truncated = rest[:-1] if last_user else rest[:]
        while truncated and total > _MAX_CONTEXT_TOKENS:
            dropped = truncated.pop(0)
            total -= len(dropped.get("content", "")) // 4

        result = ([system] if system else []) + truncated
        if last_user:
            result.append(last_user)
        return result

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        format: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> str:
        """Send chat request to Ollama with persistent session and context truncation."""
        messages = self._truncate_context(messages)

        data = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "keep_alive": self.keep_alive,
            "think": self.think,
            "options": {
                "temperature": temperature if temperature is not None else self.temperature,
                "num_predict": self.num_predict,
            },
        }
        if format:
            data["format"] = format
        if tools:
            data["tools"] = tools

        session = await self._get_session()
        async with session.post(f"{self.base_url}/api/chat", json=data) as resp:
            if resp.status == 404:
                raise RuntimeError(f"Model '{self.model}' not found. Run: ollama pull {self.model}")
            resp_json = await resp.json()
            if "error" in resp_json:
                raise RuntimeError(f"Ollama Error: {resp_json['error']}")
            msg = resp_json.get("message", {})
            msg.pop("thinking", None)
            if msg.get("tool_calls"):
                return json.dumps({"tool_calls": msg["tool_calls"]})
            return msg.get("content") or ""

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream tokens from Ollama. Yields content strings as they arrive."""
        messages = self._truncate_context(messages)

        data = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "keep_alive": self.keep_alive,
            "think": self.think,
            "options": {
                "temperature": temperature if temperature is not None else self.temperature,
                "num_predict": self.num_predict,
            },
        }
        if tools:
            data["tools"] = tools

        session = await self._get_session()
        async with session.post(f"{self.base_url}/api/chat", json=data) as resp:
            if resp.status == 404:
                raise RuntimeError(f"Model '{self.model}' not found. Run: ollama pull {self.model}")
            async for line in resp.content:
                if not line or not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "error" in chunk:
                    raise RuntimeError(f"Ollama Error: {chunk['error']}")
                msg = chunk.get("message", {})
                if msg.get("tool_calls"):
                    yield json.dumps({"tool_calls": msg["tool_calls"]})
                content = msg.get("content", "")
                if content:
                    yield content

    async def structured_output(
        self, prompt: str, output_schema: dict[str, Any], temperature: float = 0.1
    ) -> dict[str, Any]:
        """Get structured JSON output from LLM using JSON schema."""
        messages = [
            {
                "role": "system",
                "content": "You are a precise JSON generator. Output only valid JSON matching the schema.",
            },
            {"role": "user", "content": prompt},
        ]
        response = await self.chat(messages, temperature=temperature, format="json")
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            import re

            match = re.search(r"\{.*\}", response, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise


_llm_client: OllamaClient | None = None


def get_llm_client() -> OllamaClient:
    """Get or create the singleton LLM client."""
    global _llm_client
    if _llm_client is None:
        _llm_client = OllamaClient()
    return _llm_client


def set_llm_client(client: OllamaClient) -> None:
    """Set the singleton LLM client (for testing)."""
    global _llm_client
    _llm_client = client

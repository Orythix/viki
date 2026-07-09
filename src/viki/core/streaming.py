"""
End-to-end token streaming for CLI, dashboard, and bridges.

Ensures every output path supports streaming delivery of tokens as they
are generated, minimizing first-token latency and perceived wait time.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StreamChunk:
    """A single chunk of streamed output."""

    text: str = ""
    event: str = "token"  # token, thought, error, done, tool_call
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0


class StreamManager:
    """
    Manages streaming output across multiple consumers.

    Handles fan-out to CLI, dashboard WebSocket, and bridge clients.
    """

    def __init__(self):
        self._consumers: dict[str, list[Callable[[StreamChunk], Any]]] = {
            "token": [],
            "thought": [],
            "error": [],
            "done": [],
            "tool_call": [],
        }
        self._start_time = 0.0
        self._token_count = 0
        self._first_token_latency = 0.0

    def subscribe(self, event: str, callback: Callable[[StreamChunk], Any]) -> None:
        """Register a callback for a stream event type."""
        if event in self._consumers:
            self._consumers[event].append(callback)

    def unsubscribe(self, event: str, callback: Callable[[StreamChunk], Any]) -> None:
        if event in self._consumers and callback in self._consumers[event]:
            self._consumers[event].remove(callback)

    async def emit(self, chunk: StreamChunk) -> None:
        """Emit a chunk to all subscribed consumers."""
        chunk.timestamp = time.time()
        if chunk.event == "token":
            if self._token_count == 0:
                self._first_token_latency = time.time() - self._start_time
            self._token_count += 1
        for cb in self._consumers.get(chunk.event, []):
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(chunk)
                else:
                    cb(chunk)
            except Exception:
                logging.getLogger(__name__).warning("stream consumer callback raised")

    async def stream_text(self, text: str, event: str = "token") -> None:
        """Emit text character by character (for realistic streaming feel)."""
        # For efficiency, emit in small chunks rather than char-by-char
        chunk_size = 4
        for i in range(0, len(text), chunk_size):
            await self.emit(StreamChunk(text=text[i : i + chunk_size], event=event))
            await asyncio.sleep(0.01)
        await self.emit(StreamChunk(event="done"))

    async def emit_thought(self, text: str) -> None:
        await self.emit(StreamChunk(text=text, event="thought"))

    async def emit_error(self, text: str) -> None:
        await self.emit(StreamChunk(text=text, event="error"))

    async def emit_done(self) -> None:
        await self.emit(StreamChunk(event="done"))

    def start(self) -> None:
        """Start timing for latency measurement."""
        self._start_time = time.time()
        self._token_count = 0

    def get_stats(self) -> dict[str, Any]:
        return {
            "first_token_latency": self._first_token_latency,
            "total_tokens": self._token_count,
            "elapsed": time.time() - self._start_time if self._start_time else 0,
        }


class StreamingResponse:
    """
    Wraps an LLM streaming response for consistent consumption.

    Usage:
        response = StreamingResponse(model_router.chat_stream(prompt))
        async for chunk in response:
            print(chunk.text, end="")
    """

    def __init__(self, stream_iter: AsyncIterator[str], manager: StreamManager | None = None):
        self._iter = stream_iter
        self._manager = manager or StreamManager()
        self._full_text: list[str] = []

    def __aiter__(self):
        return self._async_generator()

    async def _async_generator(self) -> AsyncIterator[StreamChunk]:
        self._manager.start()
        try:
            async for token in self._iter:
                self._full_text.append(token)
                chunk = StreamChunk(text=token, event="token")
                await self._manager.emit(chunk)
                yield chunk
        except Exception as e:
            err = StreamChunk(text=str(e), event="error")
            await self._manager.emit(err)
            yield err
        finally:
            await self._manager.emit_done()

    @property
    def full_text(self) -> str:
        return "".join(self._full_text)

    @property
    def manager(self) -> StreamManager:
        return self._manager


# CLI streaming renderer
async def render_stream_cli(
    response: StreamingResponse,
    write: Callable[[str], Any] | None = None,
) -> str:
    """Render a streaming response to the CLI, yielding tokens as they arrive."""
    if write is None:
        import sys

        write = sys.stdout.write
    async for chunk in response:
        if chunk.event == "token":
            write(chunk.text)
        elif chunk.event == "error":
            write(f"\n[Error: {chunk.text}]\n")
        elif chunk.event == "done":
            write("\n")
    return response.full_text


# WebSocket streaming for dashboard
async def render_stream_ws(
    response: StreamingResponse,
    send_json: Callable[[dict], Any],
) -> str:
    """Render a streaming response to a WebSocket client."""
    async for chunk in response:
        payload = {"event": chunk.event, "text": chunk.text}
        if chunk.event == "done":
            payload["stats"] = response.manager.get_stats()
        await send_json(payload) if asyncio.iscoroutinefunction(send_json) else send_json(payload)
    return response.full_text

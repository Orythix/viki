"""In-memory message bus for inter-agent communication within a swarm.

Agents can publish messages to channels and subscribe to receive messages
from other agents, enabling collaborative problem-solving.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SwarmMessage:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sender_id: str = ""
    sender_name: str = ""
    channel: str = "general"
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class SwarmMessageBus:
    """Async pub/sub message bus for swarm agents."""

    def __init__(self):
        self._subscribers: dict[str, list[asyncio.Queue[SwarmMessage]]] = defaultdict(list)
        self._history: list[SwarmMessage] = []
        self._max_history = 500

    def subscribe(self, channel: str) -> asyncio.Queue[SwarmMessage]:
        queue: asyncio.Queue[SwarmMessage] = asyncio.Queue()
        self._subscribers[channel].append(queue)
        return queue

    def unsubscribe(self, channel: str, queue: asyncio.Queue[SwarmMessage]) -> None:
        subs = self._subscribers.get(channel, [])
        if queue in subs:
            subs.remove(queue)

    async def publish(self, message: SwarmMessage) -> None:
        self._history.append(message)
        if len(self._history) > self._max_history:
            self._history.pop(0)
        subs = self._subscribers.get(message.channel, []) + self._subscribers.get("*", [])
        for queue in subs:
            queue.put_nowait(message)

    def get_history(self, channel: str | None = None, limit: int = 50) -> list[SwarmMessage]:
        if channel:
            return [m for m in self._history[-limit:] if m.channel == channel]
        return list(self._history[-limit:])

    def stats(self) -> dict[str, Any]:
        return {
            "total_messages": len(self._history),
            "channels": dict(self._subscribers),
            "subscriber_count": sum(len(q) for q in self._subscribers.values()),
        }

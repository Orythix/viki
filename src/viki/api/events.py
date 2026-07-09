"""
In-process event bus for real-time notifications (Phase 7).
Powers the WebSocket gateway and internal autonomy monitoring.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any


class EventSubscription:
    def __init__(self, channels: list[str] | None = None):
        self.id = str(uuid.uuid4())
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.channels = set(channels) if channels else None

    def matches(self, channel: str) -> bool:
        if self.channels is None:
            return True
        return channel in self.channels


class EventBus:
    """
    Simple in-memory pub/sub bus for dispatching system events.
    """

    def __init__(self):
        self._subscribers: dict[str, EventSubscription] = {}
        self._lock = asyncio.Lock()

    def subscribe(self, channels: list[str] | None = None) -> EventSubscription:
        sub = EventSubscription(channels)
        self._subscribers[sub.id] = sub
        return sub

    def unsubscribe(self, sub_id: str) -> None:
        if sub_id in self._subscribers:
            del self._subscribers[sub_id]

    def publish(self, event: str, data: dict[str, Any], channel: str = "default") -> None:
        """
        Broadcast an event to all matching subscribers.
        """
        message = json.dumps({"event": event, "data": data, "channel": channel})

        for sub in list(self._subscribers.values()):
            if sub.matches(channel):
                try:
                    # We use put_nowait because we don't want to block the publisher
                    # if a subscriber's queue is full (which shouldn't happen with
                    # an unbounded asyncio.Queue).
                    sub.queue.put_nowait(message)
                except asyncio.QueueFull:
                    pass

    def stats(self) -> dict[str, Any]:
        return {"subscribers": len(self._subscribers)}


_GLOBAL_BUS: EventBus | None = None


def get_event_bus() -> EventBus:
    global _GLOBAL_BUS
    if _GLOBAL_BUS is None:
        _GLOBAL_BUS = EventBus()
    return _GLOBAL_BUS

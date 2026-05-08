"""
P1: process-wide event bus shared between SSE + WebSocket consumers.

We deliberately keep this in-process (no Redis / Kafka). The bus is a fan-out
of `Subscriber` objects, each holding a thread-safe queue. Producers (mission
control, sub-agents, controller hooks) call `publish(kind, payload)`; every
subscriber receives the event.

This is intentionally tiny so unit tests don't need a real WS server.
"""
from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from typing import Any, Dict, List, Optional


class _Subscriber:
    def __init__(self, sub_id: str, channels: Optional[List[str]] = None, max_queued: int = 256):
        self.id = sub_id
        self.channels = set(channels) if channels else None
        self.queue: queue.Queue = queue.Queue(maxsize=max_queued)
        self.created_at = time.time()


class EventBus:
    def __init__(self):
        self._subs: Dict[str, _Subscriber] = {}
        self._lock = threading.Lock()

    def subscribe(self, channels: Optional[List[str]] = None) -> _Subscriber:
        sub = _Subscriber(uuid.uuid4().hex[:8], channels=channels)
        with self._lock:
            self._subs[sub.id] = sub
        return sub

    def unsubscribe(self, sub_id: str) -> None:
        with self._lock:
            self._subs.pop(sub_id, None)

    def publish(self, kind: str, payload: Any, channel: str = "default") -> None:
        evt = {"event": kind, "channel": channel, "ts": time.time(), "data": payload}
        encoded = json.dumps(evt, default=str)
        with self._lock:
            subs = list(self._subs.values())
        for sub in subs:
            if sub.channels is not None and channel not in sub.channels:
                continue
            try:
                sub.queue.put_nowait(encoded)
            except queue.Full:
                # Drop oldest to make room.
                try:
                    sub.queue.get_nowait()
                    sub.queue.put_nowait(encoded)
                except Exception:
                    pass

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "subscribers": len(self._subs),
                "ids": list(self._subs.keys()),
            }


_global_bus: Optional[EventBus] = None
_bus_lock = threading.Lock()


def get_event_bus() -> EventBus:
    global _global_bus
    if _global_bus is None:
        with _bus_lock:
            if _global_bus is None:
                _global_bus = EventBus()
    return _global_bus

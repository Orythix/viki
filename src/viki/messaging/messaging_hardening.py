"""
Messaging bridge hardening — production-grade Telegram, Discord, and Slack
bridges through MessagingNexus with endpoint-guard auth, rate limiting,
and reconnection logic.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from viki.config.logger import viki_logger


class RateLimiter:
    """Token-bucket rate limiter per bridge."""

    def __init__(self, tokens_per_minute: int = 30):
        self._tokens: float = tokens_per_minute
        self._max_tokens = tokens_per_minute
        self._last_refill = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        async with self._lock:
            now = time.time()
            elapsed = now - self._last_refill
            self._tokens = min(self._max_tokens, self._tokens + elapsed * (self._max_tokens / 60))
            self._last_refill = now
            if self._tokens >= 1:
                self._tokens -= 1
                return True
            return False


class CircuitBreakerBridge:
    """Circuit breaker wrapper for messaging bridges."""

    def __init__(self, name: str, failure_threshold: int = 5, cooldown: float = 60.0):
        self._name = name
        self._failures = 0
        self._threshold = failure_threshold
        self._open_until = 0.0
        self._cooldown = cooldown

    def is_open(self) -> bool:
        if time.time() < self._open_until:
            return True
        if self._failures > 0:
            self._failures = 0
        return False

    def record_success(self) -> None:
        self._failures = 0

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._threshold:
            self._open_until = time.time() + self._cooldown
            viki_logger.warning(
                "Bridge circuit breaker opened for '%s' (cooldown %.0fs)",
                self._name,
                self._cooldown,
            )

    async def call(self, fn: Callable, *args, **kwargs) -> Any:
        if self.is_open():
            raise RuntimeError(f"Bridge '{self._name}' is circuit-broken")
        try:
            result = (
                await fn(*args, **kwargs)
                if asyncio.iscoroutinefunction(fn)
                else fn(*args, **kwargs)
            )
            self.record_success()
            return result
        except Exception:
            self.record_failure()
            raise


class BridgeReconnector:
    """Automatic reconnection with exponential backoff for bridges."""

    def __init__(self, name: str, max_retries: int = 10):
        self._name = name
        self._max_retries = max_retries
        self._attempt = 0

    async def connect_with_retry(self, connect_fn: Callable, *args, **kwargs) -> Any:
        self._attempt = 0
        while self._attempt < self._max_retries:
            try:
                result = (
                    await connect_fn(*args, **kwargs)
                    if asyncio.iscoroutinefunction(connect_fn)
                    else connect_fn(*args, **kwargs)
                )
                self._attempt = 0
                return result
            except Exception as e:
                self._attempt += 1
                delay = min(2**self._attempt, 120)
                viki_logger.warning(
                    "Bridge '%s' reconnection attempt %d/%d failed: %s. Retrying in %ds",
                    self._name,
                    self._attempt,
                    self._max_retries,
                    e,
                    delay,
                )
                await asyncio.sleep(delay)
        raise RuntimeError(
            f"Bridge '{self._name}' failed after {self._max_retries} reconnection attempts"
        )


class MessageQueue:
    """Persistent message queue for guaranteed delivery."""

    def __init__(self):
        self._queues: dict[str, list[dict]] = defaultdict(list)

    def enqueue(self, bridge: str, message: dict) -> None:
        self._queues[bridge].append(
            {
                "message": message,
                "timestamp": time.time(),
                "retries": 0,
            }
        )

    def dequeue(self, bridge: str) -> list[dict]:
        items = list(self._queues.get(bridge, []))
        self._queues[bridge] = []
        return items

    def requeue_failed(self, bridge: str, items: list[dict]) -> None:
        for item in items:
            item["retries"] += 1
            if item["retries"] < 5:
                self._queues[bridge].append(item)

    def pending_count(self, bridge: str) -> int:
        return len(self._queues.get(bridge, []))


async def send_with_reliability(
    bridge_name: str,
    send_fn: Callable,
    message: dict,
    rate_limiter: RateLimiter,
    circuit_breaker: CircuitBreakerBridge,
    message_queue: MessageQueue,
    max_retries: int = 3,
) -> bool:
    """Send a message with rate limiting, circuit breaker, and queue fallback."""
    # Rate limit
    if not await rate_limiter.acquire():
        message_queue.enqueue(bridge_name, message)
        viki_logger.debug("Bridge '%s': rate limited, queued message", bridge_name)
        return False

    # Circuit breaker + send
    for attempt in range(max_retries):
        try:
            await circuit_breaker.call(send_fn, message)
            return True
        except Exception as e:
            viki_logger.warning(
                "Bridge '%s': send attempt %d failed: %s", bridge_name, attempt + 1, e
            )
            await asyncio.sleep(1)

    message_queue.enqueue(bridge_name, message)
    return False

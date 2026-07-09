"""
Heterogeneous inference pool — route heavy deliberation to the desktop GPU
from any device on the LAN.

Extends ModelRouter with a pool of inference backends across networked devices.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import cast

from viki.config.logger import viki_logger


@dataclass
class InferenceNode:
    """A network-accessible inference endpoint."""

    id: str
    name: str
    url: str
    model: str = ""
    provider: str = "openai-compatible"
    priority: int = 50
    max_tokens_per_second: float = 0.0
    latency_p95_ms: float = 0.0
    is_local: bool = True
    is_available: bool = True
    last_health_check: float = 0.0
    current_load: int = 0  # concurrent requests
    max_load: int = 4
    supported_models: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "model": self.model,
            "provider": self.provider,
            "priority": self.priority,
            "max_tokens_per_second": self.max_tokens_per_second,
            "latency_p95_ms": self.latency_p95_ms,
            "is_local": self.is_local,
            "is_available": self.is_available,
            "current_load": self.current_load,
            "max_load": self.max_load,
        }


class InferencePool:
    """
    Pool of inference nodes across LAN devices.

    Routes requests to the best available node based on:
    - Model availability
    - Current load
    - Historical latency
    - Priority (local preferred)

    Usage:
        pool = InferencePool()
        pool.register_node(InferenceNode(id="desktop-gpu", url="http://192.168.1.100:11434", ...))
        result = await pool.infer("gpt-4", prompt)
    """

    def __init__(self):
        self._nodes: dict[str, InferenceNode] = {}
        self._health_task: asyncio.Task | None = None
        self._running = False

    def register_node(self, node: InferenceNode) -> str:
        self._nodes[node.id] = node
        viki_logger.info("InferencePool: registered node '%s' at %s", node.name, node.url)
        return node.id

    def unregister_node(self, node_id: str) -> None:
        self._nodes.pop(node_id, None)

    def list_nodes(self) -> list[InferenceNode]:
        return list(self._nodes.values())

    def get_node(self, node_id: str) -> InferenceNode | None:
        return self._nodes.get(node_id)

    def select_node(self, model: str = "", preferred_node: str = "") -> InferenceNode | None:
        """Select the best node for inference."""
        candidates = [
            n
            for n in self._nodes.values()
            if n.is_available
            and n.current_load < n.max_load
            and (not model or model in n.supported_models or not n.supported_models)
        ]

        if preferred_node and preferred_node in self._nodes:
            node = self._nodes[preferred_node]
            if node.is_available and node.current_load < node.max_load:
                return node

        if not candidates:
            return None

        # Sort by: priority (higher first), load (lower first), latency (lower first)
        candidates.sort(
            key=lambda n: (-n.priority, n.current_load / max(n.max_load, 1), n.latency_p95_ms)
        )
        return candidates[0]

    async def infer(self, model: str, prompt: list[dict], node_id: str = "", **kwargs) -> str:
        """Run inference on the best available node."""
        node = self.select_node(model=model, preferred_node=node_id)
        if node is None:
            raise RuntimeError("No available inference node")

        node.current_load += 1
        try:
            start = time.perf_counter()
            result = await self._call_node(node, prompt, **kwargs)
            elapsed = (time.perf_counter() - start) * 1000
            node.latency_p95_ms = node.latency_p95_ms * 0.9 + elapsed * 0.1
            return result
        finally:
            node.current_load = max(0, node.current_load - 1)

    async def _call_node(self, node: InferenceNode, prompt: list[dict], **kwargs) -> str:
        """Make the actual API call to an inference node."""
        import aiohttp

        payload = {
            "model": node.model or kwargs.get("model", ""),
            "messages": prompt,
            "stream": False,
            **{k: v for k, v in kwargs.items() if k not in ("model", "messages", "stream")},
        }
        async with aiohttp.ClientSession() as session:
            url = f"{node.url.rstrip('/')}/v1/chat/completions"
            async with session.post(url, json=payload, timeout=120) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise RuntimeError(
                        f"Inference node '{node.name}' returned HTTP {resp.status}: {error_text}"
                    )
                data = await resp.json()
                return cast("str", data["choices"][0]["message"]["content"])

    async def start_health_checks(self, interval: int = 30) -> None:
        """Start periodic health checks on all nodes."""
        self._running = True
        while self._running:
            for node in list(self._nodes.values()):
                await self._check_health(node)
            await asyncio.sleep(interval)

    async def stop_health_checks(self) -> None:
        self._running = False
        if self._health_task:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass

    async def _check_health(self, node: InferenceNode) -> None:
        """Check if a node is responsive."""
        try:
            import aiohttp

            url = (
                f"{node.url.rstrip('/')}/api/tags"
                if "ollama" in node.url.lower()
                else f"{node.url.rstrip('/')}/v1/models"
            )
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=5) as resp:
                    node.is_available = resp.status == 200
        except Exception:
            node.is_available = False

        node.last_health_check = time.time()

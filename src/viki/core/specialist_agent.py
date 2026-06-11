"""
Sub-agent spawning with isolated memory and parent inbox/outbox.

Phase 4 — long-horizon autonomy. Replaces the flat asyncio.gather pattern in
the legacy SwarmSkill with a hierarchical, capability-scoped sub-agent that:

    * runs in its own asyncio task,
    * keeps its own scratchpad memory (no leakage into the parent's
      WorkingMemory),
    * exchanges messages with the parent through bounded asyncio queues,
    * exposes an explicit capability scope (a subset of the parent's caps),
    * is killable from the parent via cancel().

Designed to be model-agnostic: a sub-agent only needs an async `run` callable
and a capability scope; it does not rely on the global controller's ReAct loop.
"""

from __future__ import annotations

import asyncio
import builtins
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from viki.config.logger import viki_logger


@dataclass
class AgentMessage:
    """Inbox/outbox message between parent and sub-agent."""

    sender: str
    body: Any
    tag: str = "info"
    ts: float = field(default_factory=time.time)


SubAgentRunner = Callable[["SubAgent"], Awaitable[Any]]


class SubAgent:
    """
    A child agent running in its own asyncio task with isolated memory and a
    bounded message channel.

    Lifecycle:
        agent = SubAgent("researcher", capabilities={"internet_research"})
        agent.spawn(my_runner)    # starts the asyncio task
        await agent.send("hi")    # parent -> child (inbox)
        msg = await agent.recv()  # child -> parent (outbox)
        ... await agent.join()
    """

    def __init__(
        self,
        name: str,
        capabilities: set[str] | None = None,
        inbox_max: int = 64,
        outbox_max: int = 64,
        parent: str | None = None,
    ):
        self.id = uuid.uuid4().hex[:8]
        self.name = name
        self.parent = parent
        self.capabilities: set[str] = set(capabilities or set())
        self.scratchpad: list[dict[str, Any]] = []
        self.metadata: dict[str, Any] = {}
        self.inbox: asyncio.Queue[AgentMessage] = asyncio.Queue(maxsize=inbox_max)
        self.outbox: asyncio.Queue[AgentMessage] = asyncio.Queue(maxsize=outbox_max)
        self._task: asyncio.Task | None = None
        self.result: Any = None
        self.error: str | None = None
        self.started_at: float | None = None
        self.finished_at: float | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def has_capability(self, name: str) -> bool:
        return name in self.capabilities

    def remember(self, role: str, content: str) -> None:
        """Append to the sub-agent's isolated scratchpad."""
        self.scratchpad.append({"role": role, "content": content, "ts": time.time()})

    def spawn(self, runner: SubAgentRunner) -> asyncio.Task:
        """Launch the sub-agent's runner inside the current event loop."""
        if self.is_running:
            raise RuntimeError(f"SubAgent {self.id} already running")
        self.started_at = time.time()

        async def _wrapper():
            try:
                self.result = await runner(self)
            except asyncio.CancelledError:
                self.error = "cancelled"
                raise
            except Exception as e:
                self.error = str(e)
                viki_logger.warning("SubAgent[%s/%s]: runner error: %s", self.name, self.id, e)
            finally:
                self.finished_at = time.time()

        self._task = asyncio.create_task(_wrapper(), name=f"subagent-{self.name}-{self.id}")
        return self._task

    async def send(self, body: Any, tag: str = "info") -> None:
        """Parent -> sub-agent."""
        await self.inbox.put(AgentMessage(sender=self.parent or "parent", body=body, tag=tag))

    async def recv(self, timeout: float | None = None) -> AgentMessage | None:
        """Sub-agent -> parent (consume outbox)."""
        try:
            if timeout is None:
                return await self.outbox.get()
            return await asyncio.wait_for(self.outbox.get(), timeout=timeout)
        except TimeoutError:
            return None

    async def emit(self, body: Any, tag: str = "info") -> None:
        """Used by the runner to push to the parent's outbox."""
        await self.outbox.put(AgentMessage(sender=self.name, body=body, tag=tag))

    async def pull(self, timeout: float | None = None) -> AgentMessage | None:
        """Used by the runner to pull from the parent's inbox."""
        try:
            if timeout is None:
                return await self.inbox.get()
            return await asyncio.wait_for(self.inbox.get(), timeout=timeout)
        except TimeoutError:
            return None

    def cancel(self) -> None:
        """Cooperatively kill the sub-agent."""
        if self._task and not self._task.done():
            self._task.cancel()

    async def join(self, timeout: float | None = None) -> Any:
        if self._task is None:
            return self.result
        try:
            await asyncio.wait_for(self._task, timeout=timeout)
        except TimeoutError:
            self.cancel()
            raise
        except asyncio.CancelledError:
            pass
        return self.result


class SubAgentManager:
    """
    Tracks live sub-agents for a single parent. Keeps a registry so the
    controller can list / cancel / inspect children.
    """

    def __init__(self):
        self._agents: dict[str, SubAgent] = {}

    def register(self, agent: SubAgent) -> None:
        self._agents[agent.id] = agent

    def list(self) -> builtins.list[dict[str, Any]]:
        return [
            {
                "id": a.id,
                "name": a.name,
                "running": a.is_running,
                "started_at": a.started_at,
                "finished_at": a.finished_at,
                "error": a.error,
                "capabilities": sorted(a.capabilities),
            }
            for a in self._agents.values()
        ]

    def get(self, agent_id: str) -> SubAgent | None:
        return self._agents.get(agent_id)

    async def cancel_all(self) -> None:
        for a in list(self._agents.values()):
            a.cancel()
        for a in list(self._agents.values()):
            try:
                await a.join(timeout=1.0)
            except Exception:
                pass

    def prune_finished(self) -> int:
        before = len(self._agents)
        self._agents = {k: v for k, v in self._agents.items() if v.is_running}
        return before - len(self._agents)

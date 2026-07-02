"""
Hierarchical mission graph (Phase 4 — long-horizon autonomy).

Extends `viki.core.mission_control.Mission` from a flat list of repeating
directives into a directed graph of nodes that can each spawn sub-tasks,
persist across restarts, and be resumed mid-flight.

Designed to interop with the existing MissionControl loop so we do not break
the autonomy engine; a `MissionGraph` lives inside a single `Mission` and lets
that mission carry sub-state.

Node lifecycle:
    pending -> running -> done
                       \\-> failed -> retry (planner-rewrite) -> running
                       \\-> blocked (waiting on user / external)

State is persisted to JSON in the system data dir so a process restart can
resume from the last known node state.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, cast

from viki._compat import StrEnum
from viki.config.logger import viki_logger


class NodeStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    BLOCKED = "blocked"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class MissionNode:
    """A single unit of work in a mission graph."""

    id: str
    title: str
    description: str = ""
    parent_id: str | None = None
    depends_on: list[str] = field(default_factory=list)
    skill: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    status: NodeStatus = NodeStatus.PENDING
    attempts: int = 0
    max_attempts: int = 3
    result: str | None = None
    error: str | None = None
    started_at: float | None = None
    completed_at: float | None = None
    artifacts: list[str] = field(default_factory=list)
    sub_agent_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MissionNode:
        if "status" in data and isinstance(data["status"], str):
            data = dict(data)
            data["status"] = NodeStatus(data["status"])
        return cls(**data)


@dataclass
class MissionGraph:
    """
    A directed graph of MissionNodes belonging to a single mission. Nodes can
    declare dependencies on each other; the executor only runs nodes whose
    dependencies are DONE.
    """

    mission_id: str
    goal: str
    nodes: dict[str, MissionNode] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def add_node(self, node: MissionNode) -> str:
        self.nodes[node.id] = node
        self.updated_at = time.time()
        return node.id

    def add(
        self,
        title: str,
        description: str = "",
        parent_id: str | None = None,
        depends_on: list[str] | None = None,
        skill: str | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> str:
        node = MissionNode(
            id=uuid.uuid4().hex[:8],
            title=title,
            description=description,
            parent_id=parent_id,
            depends_on=depends_on or [],
            skill=skill,
            parameters=parameters or {},
        )
        return self.add_node(node)

    def ready_nodes(self) -> list[MissionNode]:
        out: list[MissionNode] = []
        for n in self.nodes.values():
            if n.status != NodeStatus.PENDING:
                continue
            if all(
                self.nodes[d].status == NodeStatus.DONE for d in n.depends_on if d in self.nodes
            ):
                out.append(n)
        return out

    def is_done(self) -> bool:
        if not self.nodes:
            return False
        terminal = {NodeStatus.DONE, NodeStatus.FAILED, NodeStatus.CANCELLED}
        return all(n.status in terminal for n in self.nodes.values())

    def has_active(self) -> bool:
        return any(n.status == NodeStatus.RUNNING for n in self.nodes.values())

    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {s.value: 0 for s in NodeStatus}
        for n in self.nodes.values():
            counts[n.status.value] += 1
        counts["total"] = len(self.nodes)
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "goal": self.goal,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "nodes": [n.to_dict() for n in self.nodes.values()],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MissionGraph:
        g = cls(
            mission_id=data["mission_id"],
            goal=data["goal"],
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
        )
        for nd in data.get("nodes", []):
            n = MissionNode.from_dict(nd)
            g.nodes[n.id] = n
        return g


SkillCallback = Callable[[MissionNode], Awaitable[str]]


class MissionGraphRunner:
    """
    Executes a MissionGraph by repeatedly walking ready nodes and dispatching
    them either to a registered skill callback or to a generic controller.
    """

    def __init__(
        self,
        controller: Any = None,
        callbacks: dict[str, SkillCallback] | None = None,
        persistence_path: str | None = None,
        max_parallel: int = 3,
    ):
        self.controller = controller
        self.callbacks = callbacks or {}
        self.persistence_path = persistence_path
        self.max_parallel = max(1, int(max_parallel))
        self._cancel = asyncio.Event()

    async def run(self, graph: MissionGraph) -> MissionGraph:
        viki_logger.info(
            "MissionGraph[%s]: starting goal=%r nodes=%d",
            graph.mission_id,
            graph.goal,
            len(graph.nodes),
        )
        while not graph.is_done() and not self._cancel.is_set():
            ready = graph.ready_nodes()
            if not ready:
                if graph.has_active():
                    await asyncio.sleep(0.05)
                    continue
                # No ready, no active -> remaining nodes are blocked.
                viki_logger.info(
                    "MissionGraph[%s]: no ready nodes; %d remaining considered blocked.",
                    graph.mission_id,
                    sum(1 for n in graph.nodes.values() if n.status == NodeStatus.PENDING),
                )
                for n in graph.nodes.values():
                    if n.status == NodeStatus.PENDING:
                        n.status = NodeStatus.BLOCKED
                break
            batch = ready[: self.max_parallel]
            await asyncio.gather(*(self._run_node(graph, n) for n in batch))
            self._persist(graph)
        self._persist(graph)
        viki_logger.info(
            "MissionGraph[%s]: finished. summary=%s",
            graph.mission_id,
            graph.summary(),
        )
        return graph

    def cancel(self) -> None:
        self._cancel.set()

    async def _run_node(self, graph: MissionGraph, node: MissionNode) -> None:
        node.status = NodeStatus.RUNNING
        node.attempts += 1
        node.started_at = time.time()
        viki_logger.info(
            "MissionGraph[%s]: running node %s (%s) attempt=%d",
            graph.mission_id,
            node.id,
            node.title,
            node.attempts,
        )
        try:
            cb = self.callbacks.get(node.skill or "") if node.skill else None
            if cb is None and self.controller is not None and node.skill:
                cb = self._make_controller_callback(node.skill)
            if cb is None:
                cb = self._noop_callback
            result = await cb(node)
            node.result = str(result) if result is not None else ""
            node.status = NodeStatus.DONE
            node.completed_at = time.time()
        except Exception as e:
            node.error = str(e)
            node.completed_at = time.time()
            if node.attempts >= node.max_attempts:
                node.status = NodeStatus.FAILED
                viki_logger.warning(
                    "MissionGraph[%s]: node %s failed permanently after %d attempts: %s",
                    graph.mission_id,
                    node.id,
                    node.attempts,
                    e,
                )
            else:
                node.status = NodeStatus.PENDING
                viki_logger.info(
                    "MissionGraph[%s]: node %s failed (attempt %d/%d), will retry: %s",
                    graph.mission_id,
                    node.id,
                    node.attempts,
                    node.max_attempts,
                    e,
                )

    def _make_controller_callback(self, skill_name: str) -> SkillCallback:
        async def _run(n: MissionNode) -> str:
            registry = getattr(self.controller, "skill_registry", None)
            if registry is None:
                raise RuntimeError("Controller has no skill_registry")
            skill = registry.get_skill(skill_name)
            if skill is None:
                raise RuntimeError(f"Skill {skill_name!r} not found on controller")
            return cast("str", await skill.execute(n.parameters or {}))

        return _run

    @staticmethod
    async def _noop_callback(n: MissionNode) -> str:
        return f"noop:{n.title}"

    def _persist(self, graph: MissionGraph) -> None:
        if not self.persistence_path:
            return
        try:
            os.makedirs(os.path.dirname(self.persistence_path) or ".", exist_ok=True)
            with open(self.persistence_path, "w", encoding="utf-8") as f:
                json.dump(graph.to_dict(), f, indent=2)
        except Exception as e:
            viki_logger.debug("MissionGraph persist failed: %s", e)


def load_graph(path: str) -> MissionGraph | None:
    """Resume a saved mission graph from disk."""
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return MissionGraph.from_dict(json.load(f))
    except Exception as e:
        viki_logger.warning("MissionGraph load failed (%s): %s", path, e)
        return None

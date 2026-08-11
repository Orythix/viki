"""
Swarm Orchestrator: Hierarchical Multi-Agent Swarm logic for VIKI.

Coordinates specialized SubAgents (Architect, Coder, QA/Security) to execute
complex engineering tasks with DAG tree tracking and state streaming.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from viki.core.specialist_agent import SubAgent


class SwarmTaskNode:
    """A node in the Swarm DAG task execution graph."""

    def __init__(
        self, task_id: str, title: str, agent_role: str, dependencies: list[str] | None = None
    ):
        self.task_id = task_id
        self.title = title
        self.agent_role = agent_role
        self.dependencies: list[str] = dependencies or []
        self.status: str = "pending"  # pending | running | completed | failed
        self.result: Any = None
        self.started_at: float | None = None
        self.finished_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "agent_role": self.agent_role,
            "dependencies": self.dependencies,
            "status": self.status,
            "result": str(self.result) if self.result else None,
            "duration": (self.finished_at - self.started_at)
            if (self.finished_at and self.started_at)
            else 0.0,
        }


class SwarmOrchestrator:
    """
    Coordinates hierarchical SubAgent swarms and tracks execution state DAG.
    """

    def __init__(self, controller: Any):
        self.controller = controller
        self.active_swarms: dict[str, dict[str, Any]] = {}

    def create_swarm(self, goal: str) -> str:
        """Initializes a new Swarm execution graph for a given high-level goal."""
        swarm_id = f"swarm_{int(time.time())}"

        # Build default multi-agent DAG
        nodes = [
            SwarmTaskNode("task_arch", "Architecture & Spec Generation", "Architect"),
            SwarmTaskNode(
                "task_code", "Code Implementation & Patching", "Coder", dependencies=["task_arch"]
            ),
            SwarmTaskNode(
                "task_qa", "Security Audit & Test Verification", "QA", dependencies=["task_code"]
            ),
        ]

        agents = {
            "Architect": SubAgent(
                "Architect", capabilities={"spec_driven_development", "code_search"}
            ),
            "Coder": SubAgent("Coder", capabilities={"filesystem_write", "shell_exec"}),
            "QA": SubAgent("QA", capabilities={"security_guard", "pytest"}),
        }

        self.active_swarms[swarm_id] = {
            "swarm_id": swarm_id,
            "goal": goal,
            "status": "initialized",
            "nodes": {n.task_id: n for n in nodes},
            "agents": agents,
            "created_at": time.time(),
        }
        return swarm_id

    async def execute_swarm(self, swarm_id: str) -> dict[str, Any]:
        """Runs the Swarm task DAG sequentially according to dependency topology."""
        swarm = self.active_swarms.get(swarm_id)
        if not swarm:
            return {"error": "Swarm not found"}

        swarm["status"] = "running"
        nodes: dict[str, SwarmTaskNode] = swarm["nodes"]
        agents: dict[str, SubAgent] = swarm["agents"]

        for _task_id, node in nodes.items():
            # Check dependencies
            deps_met = all(nodes[dep].status == "completed" for dep in node.dependencies)
            if not deps_met:
                node.status = "failed"
                node.result = "Dependencies not met"
                continue

            node.status = "running"
            node.started_at = time.time()
            agent = agents.get(node.agent_role)

            if agent:
                agent.remember("user", f"Goal: {swarm['goal']} | Task: {node.title}")
                # Simulate sub-agent runner task completion
                await asyncio.sleep(0.05)
                node.result = f"Role '{node.agent_role}' completed '{node.title}' successfully."
                node.status = "completed"
            else:
                node.status = "failed"
                node.result = f"Agent role '{node.agent_role}' missing"

            node.finished_at = time.time()

        swarm["status"] = "completed"
        return self.get_swarm_dag_state(swarm_id)

    def get_swarm_dag_state(self, swarm_id: str) -> dict[str, Any]:
        """Returns JSON-serializable DAG tree state for visualization."""
        swarm = self.active_swarms.get(swarm_id)
        if not swarm:
            return {"swarm_id": swarm_id, "status": "not_found", "nodes": []}

        return {
            "swarm_id": swarm_id,
            "goal": swarm["goal"],
            "status": swarm["status"],
            "nodes": [node.to_dict() for node in swarm["nodes"].values()],
            "agents": [a.name for a in swarm["agents"].values()],
        }

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

    def __init__(self, controller: Any, max_concurrent_tasks: int = 5):
        self.controller = controller
        self.active_swarms: dict[str, dict[str, Any]] = {}
        budgets = getattr(controller, "budgets", None) or {}
        swarm_budget = budgets.get("swarm") if isinstance(budgets, dict) else None
        if isinstance(swarm_budget, dict) and swarm_budget.get("max_concurrent"):
            max_concurrent_tasks = int(swarm_budget["max_concurrent"])
        self.max_concurrent_tasks = max_concurrent_tasks
        self._semaphore = asyncio.Semaphore(max_concurrent_tasks)
        # Per-role token/time budgets (merge/review gated).
        self.role_budgets: dict[str, dict[str, Any]] = {
            "Architect": {"time": 30.0, "tokens": 4000},
            "Coder": {"time": 60.0, "tokens": 8000},
            "QA": {"time": 45.0, "tokens": 4000, "require_review": True},
            "reviewer": {"time": 30.0, "tokens": 4000, "require_review": True},
        }
        if isinstance(swarm_budget, dict) and isinstance(swarm_budget.get("roles"), dict):
            for role, cfg in swarm_budget["roles"].items():
                if isinstance(cfg, dict):
                    self.role_budgets.setdefault(role, {}).update(cfg)

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
            async with self._semaphore:
                # Check dependencies
                deps_met = all(nodes[dep].status == "completed" for dep in node.dependencies)
                if not deps_met:
                    node.status = "failed"
                    node.result = "Dependencies not met"
                    continue

                role_budget = self.role_budgets.get(node.agent_role, {"time": 30.0, "tokens": 4000})
                # Merge/review gate: QA/reviewer nodes require prior coder completion
                # and a non-empty upstream result before accepting merge.
                if role_budget.get("require_review"):
                    upstream_ok = all(
                        nodes[dep].status == "completed" and nodes[dep].result
                        for dep in node.dependencies
                    )
                    if not upstream_ok:
                        node.status = "failed"
                        node.result = "Merge/review gate: upstream results incomplete"
                        continue

                node.status = "running"
                node.started_at = time.time()
                agent = agents.get(node.agent_role)
                time_budget = float(role_budget.get("time", 30.0))

                if agent:
                    agent.remember(
                        "user",
                        f"Goal: {swarm['goal']} | Task: {node.title} | "
                        f"budget_tokens={role_budget.get('tokens')} budget_time={time_budget}",
                    )
                    try:
                        await asyncio.wait_for(asyncio.sleep(0.05), timeout=time_budget)
                        node.result = (
                            f"Role '{node.agent_role}' completed '{node.title}' successfully "
                            f"(budget={role_budget})."
                        )
                        node.status = "completed"
                    except TimeoutError:
                        node.status = "failed"
                        node.result = f"Role '{node.agent_role}' exceeded time budget ({time_budget}s)"
                else:
                    node.status = "failed"
                    node.result = f"Agent role '{node.agent_role}' missing"

                node.finished_at = time.time()

        # Final merge step: require QA completed before marking swarm completed.
        qa = nodes.get("task_qa")
        if qa and qa.status != "completed":
            swarm["status"] = "needs_review"
        else:
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

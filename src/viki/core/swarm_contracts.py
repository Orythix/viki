"""
Swarm contracts — typed task decomposition contracts, per-agent budgets,
and merge/review steps for the SwarmOrchestrator.

Before scaling parallel sub-agents, every task is decomposed into a typed
contract that specifies inputs, outputs, budget, and review criteria.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import auto
from typing import Any

from viki._compat import StrEnum


class TaskStatus(StrEnum):
    PENDING = auto()
    ASSIGNED = auto()
    IN_PROGRESS = auto()
    COMPLETED = auto()
    FAILED = auto()
    NEEDS_REVIEW = auto()


@dataclass
class SwarmBudget:
    """Resource budget for a swarm task or agent."""

    max_tokens: int = 0  # 0 = unlimited
    max_duration_seconds: float = 300.0
    max_subtasks: int = 10
    max_retries: int = 3

    def to_dict(self) -> dict:
        return {
            "max_tokens": self.max_tokens,
            "max_duration_seconds": self.max_duration_seconds,
            "max_subtasks": self.max_subtasks,
            "max_retries": self.max_retries,
        }


@dataclass
class SwarmContract:
    """
    Typed contract for a swarm task.

    Ensures every parallel sub-agent has a clear specification before work begins.
    """

    task_id: str = ""
    name: str = ""
    description: str = ""
    input_spec: dict[str, Any] = field(default_factory=dict)
    output_spec: dict[str, Any] = field(default_factory=dict)
    budget: SwarmBudget = field(default_factory=SwarmBudget)
    status: TaskStatus = TaskStatus.PENDING
    assigned_agent: str = ""
    dependencies: list[str] = field(default_factory=list)
    created_at: float = 0.0
    started_at: float = 0.0
    completed_at: float = 0.0
    result: Any = None
    review_notes: list[str] = field(default_factory=list)
    approved: bool | None = None

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "description": self.description,
            "input_spec": self.input_spec,
            "output_spec": self.output_spec,
            "budget": self.budget.to_dict(),
            "status": self.status,
            "assigned_agent": self.assigned_agent,
            "dependencies": self.dependencies,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "approved": self.approved,
        }


class SwarmDecomposer:
    """
    Decomposes a high-level goal into typed swarm contracts.

    Handles dependency resolution and budget allocation.
    """

    def __init__(self, max_agents: int = 5):
        self._max_agents = max_agents

    def decompose(
        self,
        goal: str,
        context: dict[str, Any] | None = None,
    ) -> list[SwarmContract]:
        """
        Decompose a goal into sub-contracts.

        Returns a list of SwarmContracts with dependency ordering.
        """
        contracts: list[SwarmContract] = []
        ctx = context or {}

        # Research phase
        contracts.append(
            SwarmContract(
                task_id="research",
                name="Research",
                description=f"Research background for: {goal}",
                input_spec={"goal": goal, "context": ctx},
                output_spec={"findings": "str", "sources": "list[str]"},
                budget=SwarmBudget(max_tokens=4000, max_duration_seconds=120),
                dependencies=[],
            )
        )

        # Planning phase (depends on research)
        contracts.append(
            SwarmContract(
                task_id="plan",
                name="Planning",
                description=f"Create execution plan for: {goal}",
                input_spec={"research": "research.findings"},
                output_spec={"plan": "str", "steps": "list[str]"},
                budget=SwarmBudget(max_tokens=2000, max_duration_seconds=60),
                dependencies=["research"],
            )
        )

        # Execution phase (depends on plan)
        contracts.append(
            SwarmContract(
                task_id="execute",
                name="Execution",
                description=f"Execute the plan for: {goal}",
                input_spec={"plan": "plan.plan"},
                output_spec={"result": "str", "artifacts": "list[str]"},
                budget=SwarmBudget(max_tokens=8000, max_duration_seconds=300),
                dependencies=["plan"],
            )
        )

        # Review phase (depends on execution)
        contracts.append(
            SwarmContract(
                task_id="review",
                name="Review & Merge",
                description=f"Review and merge results for: {goal}",
                input_spec={"execution": "execute.result"},
                output_spec={"summary": "str", "approved": "bool"},
                budget=SwarmBudget(max_tokens=2000, max_duration_seconds=60),
                dependencies=["execute"],
            )
        )

        return contracts

    def assign_budgets(
        self, contracts: list[SwarmContract], total_budget: SwarmBudget
    ) -> list[SwarmContract]:
        """Distribute a total budget across contracts."""
        n = len(contracts)
        if n == 0:
            return contracts
        per_agent_tokens = total_budget.max_tokens // n if total_budget.max_tokens else 0
        per_agent_duration = (
            total_budget.max_duration_seconds / n if total_budget.max_duration_seconds else 60
        )

        for c in contracts:
            if per_agent_tokens:
                c.budget.max_tokens = min(per_agent_tokens, c.budget.max_tokens or per_agent_tokens)
            c.budget.max_duration_seconds = min(
                per_agent_duration, c.budget.max_duration_seconds or per_agent_duration
            )
            c.budget.max_subtasks = max(1, total_budget.max_subtasks // n)

        return contracts


class ContractReviewer:
    """Reviews completed swarm contract outputs."""

    def approve(self, contract: SwarmContract, notes: list[str] | None = None) -> bool:
        """Approve or reject a contract's result."""
        if contract.result is None:
            contract.approved = False
            contract.review_notes.append("No result produced")
            return False
        if notes:
            contract.review_notes.extend(notes)
        contract.approved = True
        contract.status = TaskStatus.COMPLETED
        return True

    def request_changes(self, contract: SwarmContract, feedback: str) -> None:
        """Request changes to a contract."""
        contract.status = TaskStatus.NEEDS_REVIEW
        contract.review_notes.append(f"Changes requested: {feedback}")
        contract.approved = None

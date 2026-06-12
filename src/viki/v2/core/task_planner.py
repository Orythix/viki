"""TaskPlanner — analyzes goals, generates plans, and executes multi-step tasks."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from ..llm import get_llm_client
from ..tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class TaskStep:
    id: str = ""
    description: str = ""
    tool: str = ""
    params: dict = field(default_factory=dict)
    risk: str = "LOW"
    depends_on: list[str] = field(default_factory=list)
    timeout: int = 30


@dataclass
class StepResult:
    success: bool = False
    data: Any = None
    error: str | None = None


@dataclass
class ExecutionReport:
    success: bool = False
    failed_at: str | None = None
    error: str | None = None
    results: dict[str, StepResult] = field(default_factory=dict)


@dataclass
class TaskPlan:
    goal: str = ""
    steps: list[TaskStep] = field(default_factory=list)
    estimated_complexity: str = "low"
    requires_confirmation: bool = False


class TaskPlanner:
    """Analyzes goals, generates plans, executes steps with dependency resolution.

    Independent steps are executed in parallel via ``asyncio.gather`` for
    maximum throughput.
    """

    def __init__(self, tool_registry: ToolRegistry, llm_client=None, permission_manager=None):
        self._registry = tool_registry
        self._llm = llm_client or get_llm_client()
        self._perm_manager = permission_manager

    async def create_plan(self, goal: str, context: dict | None = None) -> TaskPlan | None:
        """Analyze goal and generate a step-by-step plan using the LLM."""
        ctx = context or {}
        tools_desc = self._describe_tools()

        prompt = (
            f"You are a task planner. Break down the following goal into discrete tool-execution steps.\n\n"
            f"Goal: {goal}\n"
            f"Additional context: {ctx}\n\n"
            f"Available tools:\n{tools_desc}\n\n"
            f"Return JSON with:\n"
            f"- goal: restated goal\n"
            f"- estimated_complexity: low | medium | high\n"
            f"- requires_confirmation: boolean (true if any step is HIGH risk)\n"
            f"- steps: array of {{\n"
            f"    id: unique string,\n"
            f"    description: what this step does,\n"
            f"    tool: tool name from available tools,\n"
            f"    params: dict of parameters for the tool,\n"
            f"    risk: LOW | MEDIUM | HIGH,\n"
            f"    depends_on: list of step IDs this depends on (empty for first steps),\n"
            f"    timeout: max seconds (default 30)\n"
            f"  }}"
        )

        schema = {
            "type": "object",
            "properties": {
                "goal": {"type": "string"},
                "estimated_complexity": {"type": "string", "enum": ["low", "medium", "high"]},
                "requires_confirmation": {"type": "boolean"},
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "description": {"type": "string"},
                            "tool": {"type": "string"},
                            "params": {"type": "object"},
                            "risk": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
                            "depends_on": {"type": "array", "items": {"type": "string"}},
                            "timeout": {"type": "integer"},
                        },
                        "required": ["id", "description", "tool", "params", "risk", "depends_on"],
                    },
                },
            },
            "required": ["goal", "estimated_complexity", "requires_confirmation", "steps"],
        }

        try:
            data = await self._llm.structured_output(prompt, schema)
            steps = [TaskStep(**s) for s in data.get("steps", [])]
            plan = TaskPlan(
                goal=data.get("goal", goal),
                steps=steps,
                estimated_complexity=data.get("estimated_complexity", "low"),
                requires_confirmation=data.get("requires_confirmation", False),
            )
            return self._validate_plan(plan)
        except Exception as e:
            logger.error("TaskPlanner.create_plan failed: %s", e)
            return None

    async def execute_plan(
        self,
        plan: TaskPlan,
        session_id: str | None = None,
        max_concurrency: int = 0,
    ) -> ExecutionReport:
        """Execute plan steps with parallel execution of independent steps.

        Steps are grouped into dependency levels.  All steps within a level
        run concurrently via ``asyncio.gather``.  Levels execute sequentially.

        Parameters
        ----------
        max_concurrency :
            Max number of steps to run in parallel within a level.
            ``0`` means unlimited (all steps in the level run at once).
        """
        sorted_steps = self._topological_sort(plan.steps)
        levels = self._group_by_levels(sorted_steps)
        results: dict[str, StepResult] = {}

        for _level_idx, level in enumerate(levels):
            semaphore = asyncio.Semaphore(max_concurrency) if max_concurrency > 0 else None

            async def _run_step(step: TaskStep, _sem=semaphore) -> tuple[str, StepResult]:
                """Check permissions and execute a single step."""
                if self._perm_manager and step.risk == "HIGH":
                    check = await self._perm_manager.check(
                        step.tool, step.params, session_id or "0"
                    )
                    if not check.allowed:
                        return step.id, StepResult(
                            success=False,
                            error=f"Requires confirmation: {check.reason}",
                        )

                if _sem:
                    async with _sem:
                        return await self._execute_one(step)
                return await self._execute_one(step)

            tasks = [_run_step(s) for s in level]
            for coro in asyncio.as_completed(tasks):
                step_id, step_result = await coro
                results[step_id] = step_result

                if not step_result.success:
                    # Fail-fast: stop execution of subsequent levels
                    return ExecutionReport(
                        success=False,
                        failed_at=step_id,
                        error=step_result.error,
                        results=results,
                    )

        return ExecutionReport(success=True, results=results)

    async def _execute_one(self, step: TaskStep) -> tuple[str, StepResult]:
        """Execute a single step with timeout."""
        try:
            result = await asyncio.wait_for(
                self._registry.execute(step.tool, step.params),
                timeout=step.timeout,
            )
            step_ok = result.success if hasattr(result, "success") else bool(result)
            return step.id, StepResult(
                success=step_ok,
                data=result.data if hasattr(result, "data") else str(result),
                error=result.error if hasattr(result, "error") else None,
            )
        except TimeoutError:
            return step.id, StepResult(success=False, error=f"Timeout ({step.timeout}s)")
        except Exception as e:
            return step.id, StepResult(success=False, error=str(e))

    # ------------------------------------------------------------------
    # Dependency level grouping
    # ------------------------------------------------------------------

    @staticmethod
    def _group_by_levels(steps: list[TaskStep]) -> list[list[TaskStep]]:
        """Group topologically sorted steps into parallel execution levels.

        Returns a list of levels, where each level is a list of steps that
        can safely run in parallel.
        """
        step_map = {s.id: s for s in steps}
        depth: dict[str, int] = {}

        def _depth(sid: str) -> int:
            """Compute the dependency depth of a step (0 = no dependencies)."""
            if sid in depth:
                return depth[sid]
            step = step_map.get(sid)
            if not step or not step.depends_on:
                depth[sid] = 0
                return 0
            max_dep = max(_depth(d) for d in step.depends_on)
            depth[sid] = max_dep + 1
            return max_dep + 1

        for s in steps:
            _depth(s.id)

        max_level = max(depth.values()) if depth else 0
        levels: list[list[TaskStep]] = [[] for _ in range(max_level + 1)]
        for s in steps:
            levels[depth[s.id]].append(s)

        return levels

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_plan(self, plan: TaskPlan) -> TaskPlan:
        """Validate and clean up a plan."""
        valid_ids = {s.id for s in plan.steps}
        plan.steps = [s for s in plan.steps if s.id and s.tool]
        for step in plan.steps:
            step.depends_on = [d for d in step.depends_on if d in valid_ids]
        return plan

    @staticmethod
    def _topological_sort(steps: list[TaskStep]) -> list[TaskStep]:
        """Return steps in dependency order (dependencies first)."""
        step_map = {s.id: s for s in steps}
        visited: set[str] = set()
        result: list[TaskStep] = []

        def _visit(sid: str):
            if sid in visited:
                return
            visited.add(sid)
            step = step_map.get(sid)
            if step:
                for dep_id in step.depends_on:
                    _visit(dep_id)
                result.append(step)

        for s in steps:
            _visit(s.id)
        return result

    def _describe_tools(self) -> str:
        lines = []
        for name, tool in (
            self._registry._tools if hasattr(self._registry, "_tools") else {}
        ).items():
            lines.append(f"- {name}: {getattr(tool, 'description', '')}")
        return "\n".join(lines) or "No tools available"

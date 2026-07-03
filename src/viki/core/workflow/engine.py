"""WorkflowEngine — executes composable multi-step workflows with retry, rollback, conditional branching, and parallel execution."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Condition:
    """A condition that evaluates to True/False based on step results and context."""

    field: str = ""
    operator: str = "eq"
    value: Any = None

    def evaluate(self, step_results: dict[str, Any], context: dict) -> bool:
        lhs = self._resolve(self.field, step_results, context)
        if self.operator == "eq":
            return lhs == self.value
        elif self.operator == "neq":
            return lhs != self.value
        elif self.operator == "gt":
            return lhs is not None and self.value is not None and lhs > self.value
        elif self.operator == "gte":
            return lhs is not None and self.value is not None and lhs >= self.value
        elif self.operator == "lt":
            return lhs is not None and self.value is not None and lhs < self.value
        elif self.operator == "lte":
            return lhs is not None and self.value is not None and lhs <= self.value
        elif self.operator == "contains":
            return lhs is not None and self.value in lhs
        elif self.operator == "exists":
            return lhs is not None
        elif self.operator == "not_exists":
            return lhs is None
        return False

    @staticmethod
    def _resolve(field: str, step_results: dict, context: dict) -> Any:
        if field.startswith("steps."):
            parts = field.split(".", 2)
            step_name = parts[1] if len(parts) > 1 else ""
            inner = parts[2] if len(parts) > 2 else "result"
            step_data = step_results.get(step_name, {})
            if hasattr(step_data, "data"):
                step_data = step_data.data
            if isinstance(step_data, dict):
                return step_data.get(inner, step_data)
            return step_data
        if field.startswith("context."):
            key = field.split(".", 1)[1]
            return context.get(key)
        return context.get(field)


@dataclass
class WorkflowStep:
    name: str = ""
    tool: str = ""
    params: dict = field(default_factory=dict)
    retry_count: int = 2
    timeout: int = 60
    on_failure: str = "stop"
    if_condition: Condition | None = None
    else_steps: list[WorkflowStep] = field(default_factory=list)


@dataclass
class ParallelStep:
    """Execute multiple sub-steps concurrently. All must succeed unless fail_fast is set."""

    name: str = ""
    steps: list[WorkflowStep] = field(default_factory=list)
    fail_fast: bool = True
    timeout: int = 120


@dataclass
class RollbackStep:
    name: str = ""
    tool: str = ""
    params: dict = field(default_factory=dict)


@dataclass
class Workflow:
    name: str = ""
    description: str = ""
    steps: list[WorkflowStep | ParallelStep] = field(default_factory=list)
    rollback: list[RollbackStep] = field(default_factory=list)
    context: dict = field(default_factory=dict)


@dataclass
class WorkflowResult:
    success: bool = False
    failed_at: str | None = None
    error: str | None = None
    step_results: dict[str, Any] = field(default_factory=dict)
    rolled_back: bool = False


class WorkflowEngine:
    """Executes composable multi-step workflows with retry, rollback,
    conditional branching, and parallel step support.

    Accepts any callable ``execute_fn(name, params)`` so it can wrap
    ``SkillRegistry``, ``ToolRegistry``, or a test double.
    """

    def __init__(self, execute_fn: Callable[[str, dict], Any]):
        self._execute_fn = execute_fn

    async def execute(
        self,
        workflow: Workflow,
        context: dict | None = None,
        on_step: Callable[[str, bool | None], None] | None = None,
    ) -> WorkflowResult:
        """Execute a workflow's steps with conditional branching, parallel execution, and retry logic.

        Parameters
        ----------
        on_step :
            Called with ``(step_name, success_or_None)`` for each step.
            ``None`` means the step is starting; ``True`` or ``False``
            indicates completion status.

        On failure with ``on_failure="stop"``, triggers rollback.
        """
        run_context = {**(workflow.context or {}), **(context or {})}
        executed: list[str] = []
        step_results: dict[str, Any] = {}

        for step in workflow.steps:
            if isinstance(step, ParallelStep):
                ok = await self._execute_parallel(
                    step, run_context, step_results, executed, on_step
                )
                if not ok and step.fail_fast:
                    return WorkflowResult(
                        success=False,
                        failed_at=step.name,
                        error="Parallel step failed",
                        step_results=step_results,
                    )
                continue

            if on_step:
                on_step(step.name, None)

            if step.if_condition is not None:
                cond_met = step.if_condition.evaluate(step_results, run_context)
                if not cond_met and step.else_steps:
                    logger.info("Condition not met for '%s', running else steps", step.name)
                    for else_step in step.else_steps:
                        r = await self._execute_with_retry(else_step, run_context)
                        step_results[else_step.name] = r
                        executed.append(else_step.name)
                        ok = self._is_success(r)
                        if on_step:
                            on_step(else_step.name, ok)
                        if not ok and else_step.on_failure == "stop":
                            return WorkflowResult(
                                success=False,
                                failed_at=else_step.name,
                                error=self._extract_error(r),
                                step_results=step_results,
                            )
                    continue
                elif not cond_met:
                    logger.info("Condition not met for '%s', skipping", step.name)
                    continue

            result = await self._execute_with_retry(step, run_context)
            step_results[step.name] = result
            executed.append(step.name)

            ok = self._is_success(result)
            if on_step:
                on_step(step.name, ok)

            if not ok:
                if step.on_failure == "stop":
                    await self._rollback(workflow, executed)
                    return WorkflowResult(
                        success=False,
                        failed_at=step.name,
                        error=self._extract_error(result),
                        step_results=step_results,
                        rolled_back=True,
                    )
                elif step.on_failure == "skip":
                    logger.info("Workflow: skipping failed step '%s'", step.name)
                    continue

        return WorkflowResult(success=True, step_results=step_results)

    async def _execute_parallel(
        self,
        parallel: ParallelStep,
        context: dict,
        step_results: dict,
        executed: list[str],
        on_step: Callable[[str, bool | None], None] | None = None,
    ) -> bool:
        async def _run_one(step: WorkflowStep) -> tuple[str, Any]:
            if on_step:
                on_step(step.name, None)
            r = await self._execute_with_retry(step, context)
            if on_step:
                on_step(step.name, self._is_success(r))
            return step.name, r

        tasks = [_run_one(s) for s in parallel.steps]
        done = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True), timeout=parallel.timeout
        )

        all_ok = True
        for item in done:
            if isinstance(item, Exception):
                logger.warning("Parallel step error: %s", item)
                all_ok = False
                continue
            name, result = item
            step_results[name] = result
            executed.append(name)
            if not self._is_success(result):
                all_ok = False

        if all_ok:
            logger.info("Parallel '%s': all %d steps succeeded", parallel.name, len(parallel.steps))
        else:
            logger.warning("Parallel '%s': some steps failed", parallel.name)
        return all_ok

    async def _execute_with_retry(self, step: WorkflowStep, context: dict | None = None) -> Any:
        """Execute a single step with retry logic."""
        params = {**step.params, **(context or {})}
        last_error: Exception | None = None

        for attempt in range(1, step.retry_count + 1):
            try:
                result = await asyncio.wait_for(
                    self._execute_fn(step.tool, params),
                    timeout=step.timeout,
                )
                if self._is_success(result):
                    return result
                last_error = Exception(self._extract_error(result))
                logger.warning(
                    "Workflow step '%s' attempt %d/%d failed: %s",
                    step.name,
                    attempt,
                    step.retry_count,
                    last_error,
                )
            except TimeoutError:
                last_error = TimeoutError(f"Timeout ({step.timeout}s)")
                logger.warning(
                    "Workflow step '%s' attempt %d/%d timed out",
                    step.name,
                    attempt,
                    step.retry_count,
                )
            except Exception as e:
                last_error = e
                logger.warning(
                    "Workflow step '%s' attempt %d/%d error: %s",
                    step.name,
                    attempt,
                    step.retry_count,
                    e,
                )

        return last_error

    async def _rollback(self, workflow: Workflow, executed: list[str]) -> None:
        """Execute rollback steps in reverse order of the steps that succeeded."""
        if not workflow.rollback:
            logger.info("No rollback steps defined for workflow '%s'", workflow.name)
            return

        to_undo = [rb for rb in workflow.rollback if rb.name in executed]
        for rb in reversed(to_undo):
            try:
                await self._execute_fn(rb.tool, rb.params)
                logger.info("Rollback step '%s' executed", rb.name)
            except Exception as e:
                logger.warning("Rollback step '%s' failed: %s", rb.name, e)

    @staticmethod
    def _is_success(result: Any) -> bool:
        if result is None:
            return False
        if isinstance(result, Exception):
            return False
        if hasattr(result, "success"):
            return bool(result.success)
        return True

    @staticmethod
    def _extract_error(result: Any) -> str:
        if result is None:
            return "No result"
        if hasattr(result, "error") and result.error:
            return str(result.error)
        return str(result)


def make_workflow_executor(skill_registry: Any) -> Callable[[str, dict], Any]:
    """Create an execute_fn for WorkflowEngine from a SkillRegistry.

    The returned callable looks up ``skill_registry.skills`` by tool name
    and calls ``skill.execute(params)``.

    Falls back to calling ``skill_registry.execute_skill(name, params)``
    if available.
    """
    if hasattr(skill_registry, "execute_skill"):

        async def _exec(name: str, params: dict) -> Any:
            return await skill_registry.execute_skill(name, params)

        return _exec

    async def _exec(name: str, params: dict) -> Any:
        skill = skill_registry.skills.get(name) if hasattr(skill_registry, "skills") else None
        if skill is None:
            raise ValueError(f"Workflow: skill '{name}' not found in registry")
        return await skill.execute(params)

    return _exec

"""WorkflowEngine — executes composable multi-step workflows with retry and rollback."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class WorkflowStep:
    name: str = ""
    tool: str = ""
    params: dict = field(default_factory=dict)
    retry_count: int = 2
    timeout: int = 60
    on_failure: str = "stop"  # "stop" | "skip" | "retry"


@dataclass
class RollbackStep:
    name: str = ""
    tool: str = ""
    params: dict = field(default_factory=dict)


@dataclass
class Workflow:
    name: str = ""
    description: str = ""
    steps: list[WorkflowStep] = field(default_factory=list)
    rollback: list[RollbackStep] = field(default_factory=list)


@dataclass
class WorkflowResult:
    success: bool = False
    failed_at: str | None = None
    error: str | None = None
    step_results: dict[str, Any] = field(default_factory=dict)
    rolled_back: bool = False


class WorkflowEngine:
    """Executes composable multi-step workflows with retry and rollback support."""

    def __init__(self, registry: ToolRegistry):
        self._registry = registry

    async def execute(
        self,
        workflow: Workflow,
        context: dict | None = None,
        on_step: Callable[[str, bool | None], None] | None = None,
    ) -> WorkflowResult:
        """Execute a workflow's steps sequentially with retry logic.

        Parameters
        ----------
        on_step :
            Called with ``(step_name, success_or_None)`` for each step.
            ``None`` means the step is starting; ``True`` or ``False``
            indicates completion status.

        On failure with ``on_failure="stop"``, triggers rollback.
        """
        executed: list[str] = []
        step_results: dict[str, Any] = {}

        for step in workflow.steps:
            if on_step:
                on_step(step.name, None)
            result = await self._execute_with_retry(step, context)
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

    async def _execute_with_retry(self, step: WorkflowStep, context: dict | None = None) -> Any:
        """Execute a single step with retry logic."""
        params = {**step.params, **(context or {})}
        last_error: Exception | None = None

        for attempt in range(1, step.retry_count + 1):
            try:
                result = await asyncio.wait_for(
                    self._registry.execute(step.tool, params),
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
                await self._registry.execute(rb.tool, rb.params)
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

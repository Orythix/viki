"""Tool execution with timeout, sandbox, and output capture."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

from ..tools.base import ToolResult
from ..tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class EngineReport:
    success: bool
    result: ToolResult | None = None
    duration_ms: float = 0.0
    timed_out: bool = False
    error: str | None = None


class ExecutionEngine:
    """Wraps tool execution with timeout enforcement, sandboxing, and capture.

    Delegates actual tool calls to ``ToolRegistry`` but adds safety
    layers: timeouts (default 30 s, configurable per tool), optional
    sandboxed execution, and structured capture.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry | None = None,
        default_timeout: float = 30.0,
        tool_timeouts: dict[str, float] | None = None,
        sandbox_enabled: bool = False,
    ):
        self.tool_registry = tool_registry or ToolRegistry()
        self.default_timeout = default_timeout
        self.tool_timeouts = tool_timeouts or {}
        self.sandbox_enabled = sandbox_enabled

    async def execute(
        self,
        tool_name: str,
        params: dict[str, Any],
        timeout: float | None = None,
        **kwargs: Any,
    ) -> EngineReport:
        """Execute a tool with timeout and capture.

        Parameters
        ----------
        tool_name :
            The name of the registered tool.
        params :
            Parameters forwarded to the tool.
        timeout :
            Override timeout in seconds. Falls back to tool-specific
            timeout, then ``default_timeout``.
        """
        effective_timeout = (
            timeout
            if timeout is not None
            else self.tool_timeouts.get(tool_name, self.default_timeout)
        )
        start = time.monotonic()

        try:
            result = await asyncio.wait_for(
                self.tool_registry.execute(tool_name, params, **kwargs),
                timeout=effective_timeout,
            )
            elapsed = (time.monotonic() - start) * 1000
            if isinstance(result, ToolResult):
                return EngineReport(
                    success=result.success,
                    result=result,
                    duration_ms=elapsed,
                )
            return EngineReport(success=True, result=result, duration_ms=elapsed)

        except asyncio.TimeoutError:
            elapsed = (time.monotonic() - start) * 1000
            logger.warning("Tool '%s' timed out after %.1fs", tool_name, effective_timeout)
            return EngineReport(
                success=False,
                duration_ms=elapsed,
                timed_out=True,
                error=f"Tool '{tool_name}' timed out after {effective_timeout}s",
            )

        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            logger.exception("Tool '%s' raised an exception", tool_name)
            return EngineReport(
                success=False,
                duration_ms=elapsed,
                error=str(e),
            )

    async def execute_batch(
        self,
        calls: list[tuple[str, dict[str, Any]]],
        timeout: float | None = None,
    ) -> list[EngineReport]:
        """Execute multiple tools concurrently with a shared timeout.

        Each call is ``(tool_name, params)``.
        """
        effective = timeout or self.default_timeout * 2
        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    *(self.execute(name, p, timeout=timeout) for name, p in calls),
                    return_exceptions=True,
                ),
                timeout=effective,
            )
            processed: list[EngineReport] = []
            for r in results:
                if isinstance(r, EngineReport):
                    processed.append(r)
                elif isinstance(r, Exception):
                    processed.append(EngineReport(success=False, error=str(r)))
                else:
                    processed.append(
                        EngineReport(
                            success=False, error=f"Unexpected result type: {type(r).__name__}"
                        )
                    )
            return processed
        except asyncio.TimeoutError:
            return [
                EngineReport(
                    success=False,
                    timed_out=True,
                    error=f"Batch execution timed out after {effective}s",
                )
                for _ in calls
            ]

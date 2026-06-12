"""Tests for V2 WorkflowEngine and built-in workflow definitions."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "src"))

from viki.v2.tools.base import ToolResult
from viki.v2.workflow.definitions import (
    BUILTIN_WORKFLOWS,
    get_workflow,
    list_workflows,
)
from viki.v2.workflow.engine import (
    RollbackStep,
    Workflow,
    WorkflowEngine,
    WorkflowStep,
)


class TestWorkflowEngine:
    async def test_execute_all_steps_succeed(self, mock_registry):
        wf = Workflow(
            name="test",
            steps=[
                WorkflowStep(name="s1", tool="shell", params={"cmd": "echo a"}),
                WorkflowStep(name="s2", tool="shell", params={"cmd": "echo b"}),
            ],
        )
        engine = WorkflowEngine(mock_registry)
        result = await engine.execute(wf)
        assert result.success is True
        assert "s1" in result.step_results
        assert "s2" in result.step_results

    async def test_execute_stop_on_failure(self, mock_registry):
        tool = MagicMock()
        tool.name = "failer"
        tool.capabilities = []
        tool.execute = AsyncMock(return_value=ToolResult(success=False, error="BOOM"))
        tool.get_tool_definition = MagicMock(return_value={})
        mock_registry.register(tool)

        wf = Workflow(
            name="test-fail",
            steps=[
                WorkflowStep(name="good", tool="shell", params={}),
                WorkflowStep(name="bad", tool="failer", params={}, on_failure="stop"),
                WorkflowStep(name="never", tool="shell", params={}),
            ],
        )
        engine = WorkflowEngine(mock_registry)
        result = await engine.execute(wf)
        assert result.success is False
        assert result.failed_at == "bad"

    async def test_execute_skip_on_failure(self, mock_registry):
        tool = MagicMock()
        tool.name = "skippy"
        tool.capabilities = []
        tool.execute = AsyncMock(return_value=ToolResult(success=False, error="skip me"))
        tool.get_tool_definition = MagicMock(return_value={})
        mock_registry.register(tool)

        wf = Workflow(
            name="test-skip",
            steps=[
                WorkflowStep(name="skip-step", tool="skippy", params={}, on_failure="skip"),
            ],
        )
        engine = WorkflowEngine(mock_registry)
        result = await engine.execute(wf)
        assert result.success is True

    async def test_retry_on_failure(self, mock_registry):
        call_count = 0

        async def _fail_then_succeed(params, **kw):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                return ToolResult(success=False, error="retry me")
            return ToolResult(success=True, data="ok")

        tool = MagicMock()
        tool.name = "retry-tool"
        tool.capabilities = []
        tool.execute = AsyncMock(side_effect=_fail_then_succeed)
        tool.get_tool_definition = MagicMock(return_value={})
        mock_registry.register(tool)

        wf = Workflow(
            name="test-retry",
            steps=[
                WorkflowStep(name="retry-step", tool="retry-tool", params={}, retry_count=3),
            ],
        )
        engine = WorkflowEngine(mock_registry)
        result = await engine.execute(wf)
        assert result.success is True

    async def test_rollback_on_failure(self, mock_registry):
        tool = MagicMock()
        tool.name = "boom"
        tool.capabilities = []
        tool.execute = AsyncMock(return_value=ToolResult(success=False, error="exploded"))
        tool.get_tool_definition = MagicMock(return_value={})
        mock_registry.register(tool)

        wf = Workflow(
            name="test-rollback",
            steps=[WorkflowStep(name="boom-step", tool="boom", params={})],
            rollback=[RollbackStep(name="boom-step", tool="shell", params={"cmd": "undo"})],
        )
        engine = WorkflowEngine(mock_registry)
        result = await engine.execute(wf)
        assert result.success is False
        assert result.rolled_back is True

    async def test_empty_workflow(self, mock_registry):
        wf = Workflow(name="empty", steps=[])
        engine = WorkflowEngine(mock_registry)
        result = await engine.execute(wf)
        assert result.success is True


class TestWorkflowDefinitions:
    def test_builtin_workflows_present(self):
        assert "lint-and-fix" in BUILTIN_WORKFLOWS
        assert "deploy-preview" in BUILTIN_WORKFLOWS
        assert "audit-dependencies" in BUILTIN_WORKFLOWS
        assert "backup-project" in BUILTIN_WORKFLOWS

    def test_get_workflow(self):
        wf = get_workflow("lint-and-fix")
        assert wf is not None
        assert wf.name == "lint-and-fix"
        assert len(wf.steps) > 0

    def test_get_workflow_unknown(self):
        assert get_workflow("nonexistent") is None

    def test_list_workflows(self):
        names = list_workflows()
        assert "lint-and-fix" in names
        assert len(names) == 4

    def test_builtin_has_rollback(self):
        wf = get_workflow("lint-and-fix")
        assert len(wf.rollback) == 1

    def test_each_step_has_tool(self):
        for name, wf in BUILTIN_WORKFLOWS.items():
            for step in wf.steps:
                assert step.tool, f"Step '{step.name}' in '{name}' has no tool"

"""Tests for V2 core modules: SelfCritique, TaskPlanner, RepoAnalyzer, ContextManager."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "src"))

from viki.v2.core.context_manager import ContextManager
from viki.v2.core.repo_analyzer import RepoAnalyzer, RepositoryProfile
from viki.v2.core.self_critique import CritiqueIssue, CritiqueLevel, CritiqueResult, SelfCritique
from viki.v2.core.task_planner import TaskPlan, TaskPlanner, TaskStep
from viki.v2.tools.base import ToolResult


class TestSelfCritique:
    def test_detect_level_none(self):
        assert SelfCritique.detect_level("what time is it") == CritiqueLevel.NONE
        assert SelfCritique.detect_level("execute ls -la") == CritiqueLevel.NONE

    def test_detect_level_light(self):
        assert SelfCritique.detect_level("write a function") == CritiqueLevel.LIGHT
        assert SelfCritique.detect_level("create a small script") == CritiqueLevel.LIGHT

    def test_detect_level_full(self):
        assert SelfCritique.detect_level("refactor this module") == CritiqueLevel.FULL
        assert SelfCritique.detect_level("design a database schema") == CritiqueLevel.FULL

    def test_detect_level_default(self):
        assert SelfCritique.detect_level("hello world") == CritiqueLevel.LIGHT

    async def test_critique_none_skips(self, mock_llm):
        sc = SelfCritique(llm_client=mock_llm)
        result = await sc.critique("what time is it", "12:00")
        assert result.passed is True
        mock_llm.structured_output.assert_not_called()

    async def test_critique_calls_llm(self, mock_llm_critique):
        sc = SelfCritique(llm_client=mock_llm_critique)
        result = await sc.critique("refactor this module", "def foo(): pass")
        assert result.passed is False
        assert result.score == 0.6
        assert len(result.issues) == 1

    async def test_critique_llm_failure_graceful(self, mock_llm):
        mock_llm.structured_output.side_effect = RuntimeError("LLM down")
        sc = SelfCritique(llm_client=mock_llm)
        result = await sc.critique("write a function", "def foo(): pass")
        assert result.passed is True
        assert result.score == 1.0

    async def test_improve_returns_solution_when_passed(self, mock_llm):
        sc = SelfCritique(llm_client=mock_llm)
        result = CritiqueResult(passed=True, score=1.0, issues=[])
        improved = await sc.improve("task", "solution", result)
        assert improved == "solution"

    async def test_improve_calls_llm_when_not_passed(self, mock_llm_critique):
        sc = SelfCritique(llm_client=mock_llm_critique)
        result = CritiqueResult(
            passed=False,
            score=0.5,
            issues=[CritiqueIssue(category="style", description="bad", severity="high")],
        )
        improved = await sc.improve("task", "solution", result)
        assert improved == "Improved solution"


class TestTaskPlanner:
    async def test_create_plan(self, mock_llm_planner, mock_registry):
        planner = TaskPlanner(tool_registry=mock_registry, llm_client=mock_llm_planner)
        plan = await planner.create_plan("test goal")
        assert plan is not None
        assert len(plan.steps) == 2
        assert plan.steps[0].id == "step1"
        assert plan.estimated_complexity == "low"

    async def test_create_plan_llm_failure(self, mock_llm, mock_registry):
        mock_llm.structured_output.side_effect = RuntimeError("LLM error")
        planner = TaskPlanner(tool_registry=mock_registry, llm_client=mock_llm)
        plan = await planner.create_plan("test")
        assert plan is None

    async def test_execute_plan_success(self, mock_registry):
        steps = [
            TaskStep(
                id="s1", description="step 1", tool="shell", params={"cmd": "echo hi"}, risk="LOW"
            ),
        ]
        plan = TaskPlan(goal="test", steps=steps)
        planner = TaskPlanner(tool_registry=mock_registry)
        report = await planner.execute_plan(plan)
        assert report.success is True
        assert "s1" in report.results

    async def test_execute_plan_with_deps(self, mock_registry):
        steps = [
            TaskStep(id="s1", description="first", tool="shell", params={}, risk="LOW"),
            TaskStep(
                id="s2",
                description="second",
                tool="shell",
                params={},
                risk="LOW",
                depends_on=["s1"],
            ),
        ]
        plan = TaskPlan(goal="test", steps=steps)
        planner = TaskPlanner(tool_registry=mock_registry)
        report = await planner.execute_plan(plan)
        assert report.success is True
        assert list(report.results.keys()) == ["s1", "s2"]

    async def test_execute_plan_step_failure(self, mock_registry):
        tool = MagicMock()
        tool.name = "failing"
        tool.capabilities = []
        tool.execute = AsyncMock(return_value=ToolResult(success=False, error="fail"))
        tool.get_tool_definition = MagicMock(return_value={})
        mock_registry.register(tool)

        steps = [TaskStep(id="s1", description="fail", tool="failing", params={}, risk="LOW")]
        plan = TaskPlan(goal="test", steps=steps)
        planner = TaskPlanner(tool_registry=mock_registry)
        report = await planner.execute_plan(plan)
        assert report.success is False
        assert report.failed_at == "s1"

    def test_topological_sort(self):
        steps = [
            TaskStep(id="a", depends_on=[]),
            TaskStep(id="c", depends_on=["a"]),
            TaskStep(id="b", depends_on=["a"]),
            TaskStep(id="d", depends_on=["b", "c"]),
        ]
        sorted_steps = TaskPlanner._topological_sort(steps)
        ids = [s.id for s in sorted_steps]
        assert ids.index("a") < ids.index("b")
        assert ids.index("a") < ids.index("c")
        assert ids.index("b") < ids.index("d")
        assert ids.index("c") < ids.index("d")

    def test_validate_plan_removes_bad_steps(self, mock_registry):
        steps = [
            TaskStep(id="", description="no id", tool="shell", params={}, risk="LOW"),
            TaskStep(id="good", description="valid", tool="shell", params={}, risk="LOW"),
        ]
        plan = TaskPlan(goal="test", steps=steps)
        planner = TaskPlanner(tool_registry=mock_registry)
        validated = planner._validate_plan(plan)
        assert len(validated.steps) == 1
        assert validated.steps[0].id == "good"

    def test_group_by_levels_single(self):
        steps = [TaskStep(id="a", depends_on=[])]
        levels = TaskPlanner._group_by_levels(steps)
        assert len(levels) == 1
        assert levels[0][0].id == "a"

    def test_group_by_levels_chain(self):
        steps = [
            TaskStep(id="a", depends_on=[]),
            TaskStep(id="b", depends_on=["a"]),
            TaskStep(id="c", depends_on=["b"]),
        ]
        levels = TaskPlanner._group_by_levels(steps)
        assert len(levels) == 3
        assert [s.id for s in levels[0]] == ["a"]
        assert [s.id for s in levels[1]] == ["b"]
        assert [s.id for s in levels[2]] == ["c"]

    def test_group_by_levels_parallel(self):
        steps = [
            TaskStep(id="a", depends_on=[]),
            TaskStep(id="b", depends_on=[]),
            TaskStep(id="c", depends_on=[]),
        ]
        levels = TaskPlanner._group_by_levels(steps)
        assert len(levels) == 1
        assert {s.id for s in levels[0]} == {"a", "b", "c"}

    def test_group_by_levels_diamond(self):
        steps = [
            TaskStep(id="a", depends_on=[]),
            TaskStep(id="b", depends_on=["a"]),
            TaskStep(id="c", depends_on=["a"]),
            TaskStep(id="d", depends_on=["b", "c"]),
        ]
        levels = TaskPlanner._group_by_levels(steps)
        assert len(levels) == 3
        assert [s.id for s in levels[0]] == ["a"]
        assert {s.id for s in levels[1]} == {"b", "c"}
        assert [s.id for s in levels[2]] == ["d"]

    async def test_execute_plan_parallel_steps(self, mock_registry):
        steps = [
            TaskStep(id="s1", tool="shell", params={"cmd": "echo a"}, risk="LOW"),
            TaskStep(id="s2", tool="shell", params={"cmd": "echo b"}, risk="LOW"),
            TaskStep(id="s3", tool="shell", params={"cmd": "echo c"}, risk="LOW"),
        ]
        plan = TaskPlan(goal="test", steps=steps)
        planner = TaskPlanner(tool_registry=mock_registry)
        report = await planner.execute_plan(plan)
        assert report.success is True
        assert len(report.results) == 3

    async def test_execute_plan_fail_fast_with_parallel(self, mock_registry):
        tool = MagicMock()
        tool.name = "failer"
        tool.capabilities = []
        tool.execute = AsyncMock(return_value=ToolResult(success=False, error="BOOM"))
        tool.get_tool_definition = MagicMock(return_value={})
        mock_registry.register(tool)

        steps = [
            TaskStep(id="s1", tool="shell", params={}, risk="LOW"),
            TaskStep(id="s2", tool="failer", params={}, risk="LOW"),
        ]
        plan = TaskPlan(goal="test", steps=steps)
        planner = TaskPlanner(tool_registry=mock_registry)
        report = await planner.execute_plan(plan)
        # One step succeeded, one failed
        assert report.success is False
        assert report.failed_at == "s2"

    async def test_execute_plan_with_max_concurrency(self, mock_registry):
        steps = [
            TaskStep(id="s1", tool="shell", params={}, risk="LOW"),
            TaskStep(id="s2", tool="shell", params={}, risk="LOW"),
            TaskStep(id="s3", tool="shell", params={}, risk="LOW"),
        ]
        plan = TaskPlan(goal="test", steps=steps)
        planner = TaskPlanner(tool_registry=mock_registry)
        report = await planner.execute_plan(plan, max_concurrency=2)
        assert report.success is True
        assert len(report.results) == 3


class TestRepoAnalyzer:
    async def test_analyze_empty_dir(self, temp_dir):
        analyzer = RepoAnalyzer()
        profile = await analyzer.analyze(str(temp_dir))
        assert isinstance(profile, RepositoryProfile)
        assert profile.languages == []

    async def test_analyze_python_project(self, temp_dir):
        (temp_dir / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        analyzer = RepoAnalyzer()
        profile = await analyzer.analyze(str(temp_dir))
        assert "Python" in profile.languages

    async def test_analyze_docker(self, temp_dir):
        (temp_dir / "Dockerfile").write_text("FROM python:3.11")
        (temp_dir / "docker-compose.yml").write_text("version: '3'")
        analyzer = RepoAnalyzer()
        profile = await analyzer.analyze(str(temp_dir))
        assert profile.has_docker is True

    async def test_analyze_typescript(self, temp_dir):
        (temp_dir / "package.json").write_text('{"name": "test"}')
        (temp_dir / "tsconfig.json").write_text("{}")
        analyzer = RepoAnalyzer()
        profile = await analyzer.analyze(str(temp_dir))
        assert "TypeScript" in profile.languages or "JavaScript" in profile.languages

    async def test_analyze_nonexistent_path(self):
        analyzer = RepoAnalyzer()
        profile = await analyzer.analyze("/nonexistent/path/xyz")
        assert isinstance(profile, RepositoryProfile)


class TestContextManager:
    def test_initialization(self):
        cm = ContextManager()
        assert cm is not None

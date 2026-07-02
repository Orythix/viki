"""
Phase 3: tests for the Planner/Executor split.
"""

from __future__ import annotations

import asyncio
import json
import unittest

from viki.core.task_planner import PlannerExecutor, PlanTask, TaskGraph, TaskStatus, TaskType


class _StubModel:
    def __init__(self, response: str):
        self._response = response
        self.model_name = "stub-planner"
        self.provider_name = "stub"

    async def chat(self, messages, temperature=0.0):
        return self._response


class _StubRouter:
    def __init__(self, model):
        self.model = model

    def get_model(self, capabilities=None):
        return self.model


def _run(coro):
    return asyncio.run(coro)


class TestPlanner(unittest.TestCase):
    def test_parses_json_plan(self):
        plan_json = json.dumps(
            [
                {"id": "t1", "type": "search_repo", "description": "find foo", "parameters": {"query": "foo"}, "depends_on": []},
                {"id": "t2", "type": "patch", "description": "apply patch", "parameters": {"path": "x.py"}, "depends_on": ["t1"]},
                {"id": "t3", "type": "run_tests", "description": "verify", "parameters": {}, "depends_on": ["t2"]},
            ]
        )
        router = _StubRouter(_StubModel(plan_json))
        planner = PlannerExecutor(router)
        graph = _run(planner.plan("Refactor foo() in x.py"))
        self.assertEqual(len(graph.tasks), 3)
        self.assertEqual(graph.tasks[0].type, TaskType.SEARCH_REPO)
        self.assertEqual(graph.tasks[2].depends_on, ["t2"])

    def test_fallback_plan_when_parse_fails(self):
        router = _StubRouter(_StubModel("not json at all"))
        planner = PlannerExecutor(router)
        graph = _run(planner.plan("Some goal"))
        self.assertEqual(len(graph.tasks), 3)
        self.assertEqual(graph.tasks[0].type, TaskType.SEARCH_REPO)


class TestExecutor(unittest.TestCase):
    def test_runs_in_dependency_order(self):
        called: list[str] = []

        async def cb_search(task):
            called.append(task.id)
            return f"searched {task.parameters.get('query')}"

        async def cb_analyze(task):
            called.append(task.id)
            return "analyzed"

        async def cb_run_tests(task):
            called.append(task.id)
            return "ok"

        router = _StubRouter(_StubModel("not used"))
        planner = PlannerExecutor(
            router,
            executor_callbacks={
                TaskType.SEARCH_REPO.value: cb_search,
                TaskType.ANALYZE.value: cb_analyze,
                TaskType.RUN_TESTS.value: cb_run_tests,
            },
        )
        graph = TaskGraph(goal="test")
        graph.tasks = [
            PlanTask(id="t1", type=TaskType.SEARCH_REPO, description="search", parameters={"query": "x"}),
            PlanTask(id="t2", type=TaskType.ANALYZE, description="analyze", depends_on=["t1"]),
            PlanTask(id="t3", type=TaskType.RUN_TESTS, description="run", depends_on=["t2"]),
        ]
        graph = _run(planner.execute(graph))
        self.assertEqual(called, ["t1", "t2", "t3"])
        self.assertTrue(all(t.status == TaskStatus.DONE for t in graph.tasks))

    def test_failure_then_retry_then_fail(self):
        attempts = []

        async def cb_fail(task):
            attempts.append(task.id)
            raise RuntimeError("boom")

        router = _StubRouter(_StubModel("not used"))
        planner = PlannerExecutor(router, executor_callbacks={TaskType.ANALYZE.value: cb_fail})
        graph = TaskGraph(goal="test")
        graph.tasks = [PlanTask(id="t1", type=TaskType.ANALYZE, description="x", max_attempts=2)]
        graph = _run(planner.execute(graph))
        self.assertEqual(graph.tasks[0].status, TaskStatus.FAILED)
        self.assertGreaterEqual(graph.tasks[0].attempts, 2)


if __name__ == "__main__":
    unittest.main()

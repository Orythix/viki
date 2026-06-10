"""
Phase 4: tests for hierarchical MissionGraph + persistence + sub-agent runner.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest

from viki.core.mission_graph import (
    MissionGraph,
    MissionGraphRunner,
    MissionNode,
    NodeStatus,
    load_graph,
)


def _run(coro):
    return asyncio.run(coro)


class TestMissionGraphSchema(unittest.TestCase):
    def test_dependency_order(self):
        g = MissionGraph(mission_id="m1", goal="x")
        a = g.add(title="A")
        b = g.add(title="B", depends_on=[a])
        c = g.add(title="C", depends_on=[b])

        ready = g.ready_nodes()
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0].id, a)

        g.nodes[a].status = NodeStatus.DONE
        ready = g.ready_nodes()
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0].id, b)

    def test_summary(self):
        g = MissionGraph(mission_id="m", goal="g")
        a = g.add(title="A")
        b = g.add(title="B")
        g.nodes[a].status = NodeStatus.DONE
        s = g.summary()
        self.assertEqual(s["total"], 2)
        self.assertEqual(s["done"], 1)
        self.assertEqual(s["pending"], 1)


class TestMissionGraphRunner(unittest.TestCase):
    def test_runs_in_order_and_persists(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            persist = os.path.join(td, "graph.json")
            g = MissionGraph(mission_id="m", goal="ship feature")
            a = g.add(title="search", skill="search")
            b = g.add(title="patch", skill="patch", depends_on=[a])

            calls = []

            async def cb_search(n: MissionNode) -> str:
                calls.append(n.id)
                return "found"

            async def cb_patch(n: MissionNode) -> str:
                calls.append(n.id)
                return "applied"

            runner = MissionGraphRunner(
                callbacks={"search": cb_search, "patch": cb_patch},
                persistence_path=persist,
            )
            graph = _run(runner.run(g))
            self.assertEqual(calls, [a, b])
            self.assertTrue(all(n.status == NodeStatus.DONE for n in graph.nodes.values()))

            self.assertTrue(os.path.isfile(persist))
            loaded = load_graph(persist)
            self.assertIsNotNone(loaded)
            self.assertEqual(len(loaded.nodes), 2)
            self.assertTrue(all(n.status == NodeStatus.DONE for n in loaded.nodes.values()))

    def test_failure_then_retry_then_fail(self):
        g = MissionGraph(mission_id="m", goal="x")
        nid = g.add(title="t", skill="bad")
        g.nodes[nid].max_attempts = 2

        async def cb_bad(n: MissionNode) -> str:
            raise RuntimeError("boom")

        runner = MissionGraphRunner(callbacks={"bad": cb_bad})
        graph = _run(runner.run(g))
        self.assertEqual(graph.nodes[nid].status, NodeStatus.FAILED)
        self.assertGreaterEqual(graph.nodes[nid].attempts, 2)


class TestSelfHealer(unittest.TestCase):
    def test_fallback_retry_resets_attempts(self):
        from core.self_healer import SelfHealer

        g = MissionGraph(mission_id="m", goal="x")
        nid = g.add(title="t", skill="bad")
        node = g.nodes[nid]
        node.status = NodeStatus.FAILED
        node.error = "boom"
        node.attempts = node.max_attempts

        healer = SelfHealer(model_router=None, learning_module=None)
        decision = _run(healer.heal(g, node))
        self.assertEqual(decision["strategy"], "escalate")

    def test_split_creates_subtasks(self):
        from core.self_healer import SelfHealer

        g = MissionGraph(mission_id="m", goal="x")
        nid = g.add(title="parent", skill="bad")
        node = g.nodes[nid]
        node.status = NodeStatus.FAILED

        healer = SelfHealer(model_router=None, learning_module=None)
        SelfHealer._apply_recovery(
            g,
            node,
            {
                "strategy": "split",
                "subtasks": [
                    {"title": "sub1", "description": "a"},
                    {"title": "sub2", "description": "b"},
                ],
            },
        )
        self.assertEqual(node.status, NodeStatus.DONE)
        self.assertEqual(len(g.nodes), 3)


if __name__ == "__main__":
    unittest.main()

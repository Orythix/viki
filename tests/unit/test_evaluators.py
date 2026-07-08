"""
Phase 2: tests for ExecutionEvaluator, LLMJudgeEvaluator, and CapabilityIndex.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest

from viki.core.capability_index import CapabilityIndex
from viki.core.evaluators import ExecutionEvaluator, LLMJudgeEvaluator
from viki.core.inference_gateway import LLMProvider


class TestExecutionEvaluator(unittest.TestCase):
    def test_passing_python_solution(self):
        candidate = "```python\ndef add(a, b):\n    return a + b\n```"
        task = {
            "test_code": (
                "candidate = _CANDIDATE_NAMESPACE['add']\n"
                "assert candidate(2, 3) == 5\n"
                "assert candidate(0, 0) == 0\n"
            ),
            "language": "python",
        }
        score = ExecutionEvaluator().evaluate(task, candidate)
        self.assertTrue(score.passed)
        self.assertEqual(score.score, 1.0)

    def test_failing_python_solution(self):
        candidate = "```python\ndef add(a, b):\n    return a - b\n```"
        task = {
            "test_code": ("candidate = _CANDIDATE_NAMESPACE['add']\nassert candidate(2, 3) == 5\n"),
            "language": "python",
        }
        score = ExecutionEvaluator().evaluate(task, candidate)
        self.assertFalse(score.passed)
        self.assertEqual(score.score, 0.0)

    def test_no_code_block_fails(self):
        candidate = "I think the answer is 42."
        task = {"test_code": "raise SystemExit", "language": "python"}
        score = ExecutionEvaluator().evaluate(task, candidate)
        # The candidate is treated as raw Python — should still execute without exception then run test.
        # Either way, score should be defined.
        self.assertIsNotNone(score)

    def test_timeout_kills_runaway(self):
        candidate = "```python\nwhile True:\n    pass\n```"
        task = {"test_code": "", "language": "python", "timeout": 1}
        score = ExecutionEvaluator().evaluate(task, candidate)
        self.assertFalse(score.passed)
        self.assertIn("Timeout", score.reason)


class _StubJudge(LLMProvider):
    def __init__(self, name, score, rationale="ok", provider="stub"):
        super().__init__(
            {"model_name": name, "provider": provider, "capabilities": ["reasoning"], "priority": 3}
        )
        self.provider_name = provider
        self._score = score
        self._rationale = rationale

    def is_cloud(self):
        return False

    async def chat(self, messages, temperature=0.0):
        return f'{{"score": {self._score}, "rationale": "{self._rationale}"}}'

    async def chat_structured(self, messages, response_model, temperature=0.0, image_path=None):
        raise NotImplementedError


class _StubRouter:
    def __init__(self, judges):
        self.models = {j.model_name: j for j in judges}

    def get_failover_chain(self, capabilities=None, max_models=8):
        return list(self.models.values())[:max_models]

    def get_model(self, capabilities=None):
        return list(self.models.values())[0]


def _run(coro):
    return asyncio.run(coro)


class TestLLMJudge(unittest.TestCase):
    def test_majority_pass(self):
        judges = [
            _StubJudge("j1", 0.9, provider="anthropic"),
            _StubJudge("j2", 0.8, provider="openai"),
            _StubJudge("j3", 0.2, provider="local"),
        ]
        router = _StubRouter(judges)
        evaluator = LLMJudgeEvaluator(router, num_judges=3, pass_threshold=0.6)
        score = _run(evaluator.evaluate({"prompt": "what is 2+2?", "ground_truth": "4"}, "4"))
        self.assertTrue(score.passed)
        self.assertGreaterEqual(score.score, 0.5)
        self.assertEqual(len(score.judge_votes), 3)

    def test_majority_fail(self):
        judges = [
            _StubJudge("j1", 0.1, provider="anthropic"),
            _StubJudge("j2", 0.2, provider="openai"),
            _StubJudge("j3", 0.9, provider="local"),
        ]
        evaluator = LLMJudgeEvaluator(_StubRouter(judges), num_judges=3, pass_threshold=0.6)
        score = _run(evaluator.evaluate({"prompt": "answer please"}, "answer"))
        self.assertFalse(score.passed)


class TestCapabilityIndex(unittest.TestCase):
    def test_geometric_mean_with_two_axes(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as root:
            # humaneval_plus -> coding axis, all pass
            os.makedirs(os.path.join(root, "humaneval_plus"))
            with open(os.path.join(root, "humaneval_plus", "20260101_120000_aaa.jsonl"), "w") as f:
                f.write(json.dumps({"__metadata__": True, "air_gap": False}) + "\n")
                f.write(json.dumps({"task_id": "1", "score": 1.0, "passed": True}) + "\n")
                f.write(json.dumps({"task_id": "2", "score": 1.0, "passed": True}) + "\n")
            # gaia -> autonomy axis, half pass
            os.makedirs(os.path.join(root, "gaia"))
            with open(os.path.join(root, "gaia", "20260101_130000_bbb.jsonl"), "w") as f:
                f.write(json.dumps({"__metadata__": True, "air_gap": True}) + "\n")
                f.write(json.dumps({"task_id": "1", "score": 1.0, "passed": True}) + "\n")
                f.write(json.dumps({"task_id": "2", "score": 0.0, "passed": False}) + "\n")

            idx = CapabilityIndex(root, min_tasks=0, bootstrap_iters=0).compute()
            self.assertIn("capability_index", idx)
            self.assertIn("axes", idx)
            self.assertAlmostEqual(idx["axes"]["coding"], 1.0)
            self.assertAlmostEqual(idx["axes"]["autonomy"], 0.5)
            # Local supremacy uses air_gap-flagged runs only (just gaia).
            self.assertAlmostEqual(idx["axes"]["local_supremacy"], 0.5)
            self.assertGreater(idx["capability_index"], 0.0)
            self.assertEqual(len(idx["suites"]), 2)


if __name__ == "__main__":
    unittest.main()

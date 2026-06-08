"""
Smoke tests for the benchmark dataset adapters. These don't hit the network;
they verify that the converters correctly transform canonical examples into
the harness's task format.
"""
from __future__ import annotations

import unittest

from scripts.evals import datasets as ds


class TestConverters(unittest.TestCase):
    def test_humaneval_plus(self):
        ex = {
            "task_id": "HumanEval/0",
            "prompt": "def add(a, b):\n    \"\"\"Add two numbers.\"\"\"\n",
            "test": "def check(fn):\n    assert fn(1,2)==3",
            "entry_point": "add",
        }
        row = ds._humaneval_plus_convert(ex)
        self.assertIsNotNone(row)
        self.assertEqual(row["grader"], "execution")
        self.assertIn("check(add)", row["test_code"])

    def test_swe_bench_verified(self):
        ex = {
            "instance_id": "django__django-12345",
            "repo": "django/django",
            "base_commit": "abc",
            "problem_statement": "fix queryset bug",
            "FAIL_TO_PASS": ["t1"],
            "PASS_TO_PASS": ["t2"],
        }
        row = ds._swe_bench_convert(ex)
        self.assertIsNotNone(row)
        self.assertEqual(row["grader"], "llm")
        self.assertIn("django/django", row["prompt"])

    def test_gpqa(self):
        ex = {
            "Record ID": "r1",
            "Question": "What is 2+2?",
            "Correct Answer": "4",
            "Incorrect Answer 1": "3",
            "Incorrect Answer 2": "5",
            "Incorrect Answer 3": "6",
        }
        row = ds._gpqa_convert(ex)
        self.assertIn("(A)", row["prompt"])
        self.assertEqual(row["expected_outcome"], "4")

    def test_known_specs_present(self):
        for required in ("humaneval_plus", "swe_bench_verified", "livecodebench",
                         "gaia", "agentbench", "bigcodebench", "gpqa_diamond"):
            self.assertIn(required, ds.SPECS)


if __name__ == "__main__":
    unittest.main()

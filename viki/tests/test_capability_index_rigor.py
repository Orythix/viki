"""
P2: tests for the capability-index rigor upgrades:
- minimum-task threshold,
- bootstrap confidence intervals,
- per-suite provenance hashes.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest

from viki.core.capability_index import CapabilityIndex


def _write_suite(root: str, suite: str, run_id: str, results):
    suite_dir = os.path.join(root, suite)
    os.makedirs(suite_dir, exist_ok=True)
    path = os.path.join(suite_dir, run_id + ".jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
    return path


class TestCapabilityIndexRigor(unittest.TestCase):
    def test_min_task_threshold_disqualifies_small_suite(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            _write_suite(td, "humaneval_plus", "001",
                         [{"task_id": "t1", "score": 1.0, "passed": True}])
            ci = CapabilityIndex(td, min_tasks=20, bootstrap_iters=0)
            data = ci.compute()
            self.assertEqual(data["axes"]["coding"], 0.0)
            self.assertEqual(data["qualifying_suites"], 0)
            suite = data["suites"][0]
            self.assertFalse(suite["qualifies"])
            self.assertEqual(suite["task_count"], 1)

    def test_bootstrap_ci_attached_for_qualifying_suite(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            results = [{"task_id": f"t{i}", "score": 1.0, "passed": True} for i in range(10)]
            results += [{"task_id": f"t{i}", "score": 0.0, "passed": False} for i in range(10, 25)]
            _write_suite(td, "swe_bench_verified", "002", results)
            ci = CapabilityIndex(td, min_tasks=20, bootstrap_iters=200)
            data = ci.compute()
            suite = data["suites"][0]
            self.assertTrue(suite["qualifies"])
            self.assertGreaterEqual(suite["ci_high"], suite["ci_low"])
            self.assertGreaterEqual(suite["ci_high"], 0.0)

    def test_provenance_hash_stable(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            results = [{"task_id": f"t{i}", "score": 1.0, "passed": True} for i in range(20)]
            _write_suite(td, "gaia", "003", results)
            ci = CapabilityIndex(td, min_tasks=20, bootstrap_iters=0)
            d1 = ci.compute()
            d2 = ci.compute()
            self.assertEqual(d1["suites"][0]["provenance_sha256"],
                             d2["suites"][0]["provenance_sha256"])
            self.assertTrue(d1["suites"][0]["provenance_sha256"])


if __name__ == "__main__":
    unittest.main()

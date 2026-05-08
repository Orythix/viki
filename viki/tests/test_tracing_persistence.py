"""
Tests for parent-ID propagation and SQLite persistence in tracing.
"""
from __future__ import annotations

import os
import tempfile
import unittest

from viki.core.tracing import (
    init_persistent_traces,
    start_span,
    get_persistent_traces,
)


class TestTracingPersistence(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = os.path.join(self._td.name, "traces.db")
        init_persistent_traces(self.db_path)

    def tearDown(self):
        try:
            self._td.cleanup()
        except Exception:
            pass

    def test_parent_child_spans_share_trace_id(self):
        with start_span("outer") as outer:
            outer_trace = outer["trace_id"]
            outer_span = outer["span_id"]
            with start_span("inner") as inner:
                self.assertEqual(inner["trace_id"], outer_trace)
                self.assertEqual(inner["parent_span_id"], outer_span)

    def test_persistent_traces_grouped(self):
        with start_span("parent") as p:
            with start_span("child"):
                pass
        traces = get_persistent_traces(limit=5)
        self.assertGreaterEqual(len(traces), 1)
        first = traces[0]
        self.assertGreaterEqual(first["span_count"], 2)
        names = [s["name"] for s in first["spans"]]
        self.assertIn("parent", names)
        self.assertIn("child", names)


if __name__ == "__main__":
    unittest.main()

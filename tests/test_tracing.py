"""
Phase 6: tests for the OpenTelemetry-style tracing helper.
"""

from __future__ import annotations

import unittest

from core.telemetry_service import (
    clear_local_spans,
    get_local_spans,
    init_tracing,
    start_span,
)


class TestTracing(unittest.TestCase):
    def setUp(self):
        clear_local_spans()
        init_tracing(service_name="viki-test", export_to_stdout=False)

    def test_span_records_attributes(self):
        with start_span("unit.test", attributes={"k": "v"}) as info:
            info["attributes"]["added"] = 1
        spans = get_local_spans(limit=10)
        self.assertTrue(spans)
        latest = spans[0]
        self.assertEqual(latest["name"], "unit.test")
        self.assertEqual(latest["attributes"]["k"], "v")
        self.assertEqual(latest["attributes"]["added"], 1)
        self.assertGreaterEqual(latest["elapsed_ms"], 0.0)

    def test_nested_spans_record_separately(self):
        with start_span("outer"):
            with start_span("inner.a"):
                pass
            with start_span("inner.b"):
                pass
        names = [s["name"] for s in get_local_spans(limit=10)]
        self.assertIn("outer", names)
        self.assertIn("inner.a", names)
        self.assertIn("inner.b", names)


if __name__ == "__main__":
    unittest.main()

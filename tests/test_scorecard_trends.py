"""
P2: tests for sparkline series + regression detection on the
IntelligenceScorecard.
"""

from __future__ import annotations

import tempfile
import unittest

from viki.core.scorecard import IntelligenceScorecard


class TestScorecardTrends(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.dir = self._td.name
        self.sc = IntelligenceScorecard(self.dir)

    def tearDown(self):
        try:
            self.sc.flush()
        except Exception:
            pass
        try:
            self._td.cleanup()
        except Exception:
            pass

    def _record(self, model: str, metric: str, values):
        for v in values:
            self.sc.record_metric(metric, v, model=model)

    def test_sparkline_series_is_per_model(self):
        self._record("local-7b", "reliability_rate", [0.9, 0.85, 0.95])
        self._record("cloud-405b", "reliability_rate", [0.7, 0.72])
        series = self.sc.get_sparkline_series(points=10, model="local-7b")
        self.assertEqual(series["reliability_rate"], [0.9, 0.85, 0.95])
        all_series = self.sc.get_sparkline_series(points=10)
        self.assertEqual(len(all_series["reliability_rate"]), 5)

    def test_regression_detected(self):
        recent_low = [0.4] * 10
        prev_high = [0.95] * 10
        self._record("model-x", "reliability_rate", prev_high + recent_low)
        regs = self.sc.detect_regressions(window=10, threshold=0.05, model="model-x")
        names = [r["metric"] for r in regs]
        self.assertIn("reliability_rate", names)

    def test_no_regression_when_stable(self):
        self._record("model-y", "reliability_rate", [0.9] * 30)
        regs = self.sc.detect_regressions(window=10, threshold=0.05, model="model-y")
        self.assertEqual(regs, [])

    def test_segmented_trends_bundle(self):
        self._record("local-7b", "reliability_rate", [0.9, 0.85])
        bundle = self.sc.get_segmented_trends(points=10)
        self.assertIn("_all_", bundle)
        self.assertIn("local-7b", bundle)
        self.assertIn("series", bundle["local-7b"])
        self.assertIn("regressions", bundle["local-7b"])


if __name__ == "__main__":
    unittest.main()

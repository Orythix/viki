"""
Phase 6: HTTP endpoint smoke tests for the new API surface (SSE chat,
traces, evals, segmented scorecard, promotion state).

These tests stub the global controller so the Flask app runs without
spinning up the full agent. They guarantee that the new routes are wired
correctly and respond with the expected envelope shape.
"""

from __future__ import annotations

import asyncio
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("VIKI_API_KEY", "test-key")

from viki.api import server  # noqa: E402  (env must be set before import)
from viki.core.scorecard import IntelligenceScorecard  # noqa: E402


def _make_stub_controller():
    """Build a tiny SimpleNamespace that satisfies the endpoints we're testing."""
    sc = IntelligenceScorecard(data_dir=os.path.dirname(__file__))
    sc.record_metric("reliability_rate", 0.9, model="viki-test")

    class _Stub:
        def __init__(self):
            self.settings = {"system": {"data_dir": os.path.dirname(__file__)}}
            self.scorecard = sc
            self._meta = {"final": "ok"}

        async def process_request(self, message, **kwargs):
            on_event = kwargs.get("on_event")
            if on_event is not None:
                on_event("status", "ROUTING")
                on_event("status", "EXECUTING")
            return f"echo:{message}"

        def get_last_response_meta(self, session_id=None):
            return {
                "subtasks": [{"action": "echo", "step": 1}],
                "total_steps": 1,
                "cognitive_route": {"outcome": "shallow"},
            }

        @property
        def continuous_learner(self):
            return SimpleNamespace(get_status=lambda: {"enabled": True})

    return _Stub()


class _ApiTestBase(unittest.TestCase):
    def setUp(self):
        self.stub = _make_stub_controller()
        self._patch = patch.object(server, "get_controller", return_value=self.stub)
        self._patch.start()
        self.client = server.app.test_client()
        self.headers = {"Authorization": "Bearer test-key"}

    def tearDown(self):
        self._patch.stop()


class TestScorecardEndpoint(_ApiTestBase):
    def test_segmented_scorecard(self):
        r = self.client.get("/api/scorecard/segmented", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("_all_", data)
        self.assertIn("viki-test", data)


class TestPromotionEndpoint(_ApiTestBase):
    def test_promotion_state(self):
        r = self.client.get("/api/forge/promotion", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json().get("enabled"))


class TestTracesEndpoint(_ApiTestBase):
    def test_traces_listing(self):
        from viki.core.tracing import init_tracing, start_span

        init_tracing(service_name="viki-test", export_to_stdout=False)
        with start_span("api.test"):
            pass
        r = self.client.get("/api/traces", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertIn("spans", body)
        self.assertTrue(any(s["name"] == "api.test" for s in body["spans"]))


class TestSSEStreaming(_ApiTestBase):
    def test_chat_stream_emits_final_event(self):
        r = self.client.post(
            "/api/chat/stream",
            headers={**self.headers, "Content-Type": "application/json"},
            data=json.dumps({"message": "ping"}),
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers.get("Content-Type", "").split(";")[0], "text/event-stream")
        body = r.data.decode("utf-8")
        self.assertIn("event: final", body)
        self.assertIn("event: done", body)
        self.assertIn("echo:ping", body)


if __name__ == "__main__":
    unittest.main()

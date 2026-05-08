"""
Streaming cortex deliberation.

When `on_event` is supplied AND the input is trivial, DeliberationLayer must
consume model.chat_stream(...) and emit `partial` events for each chunk
before returning a VIKIResponse.
"""
from __future__ import annotations

import asyncio
import unittest

from viki.core.cortex import DeliberationLayer


class _FakeStreamingModel:
    model_name = "fake-stream"
    config: dict = {}

    def __init__(self, chunks):
        self._chunks = list(chunks)
        self.calls = 0

    async def chat_stream(self, messages, temperature=0.7):
        self.calls += 1
        for c in self._chunks:
            yield c

    def record_performance(self, *args, **kwargs):
        pass


class _FakeRouter:
    def __init__(self, model):
        self._model = model

    def get_model(self, capabilities=None):
        return self._model


class TestStreamingCortex(unittest.TestCase):
    def test_trivial_input_streams_partial_events(self):
        chunks = ["Hey", " there", "!"]
        model = _FakeStreamingModel(chunks)
        layer = DeliberationLayer(_FakeRouter(model), soul_config={"system_prompt": "VIKI."})

        events = []

        def on_event(kind, data):
            events.append((kind, data))

        ctx = {
            "raw_input": "hi",
            "intent_type": "conversation",
            "sentiment": "neutral",
            "recommended_capabilities": ["chatter"],
            "use_lite_schema": True,
            "action_results": [],
            "use_ensemble": False,
            "on_event": on_event,
            "conversation_history": [],
        }

        resp = asyncio.run(layer._logic(ctx))

        self.assertEqual(model.calls, 1, "chat_stream should be invoked once")
        partials = [d for k, d in events if k == "partial"]
        self.assertEqual(partials, chunks, "every chunk must surface as a partial event")
        self.assertEqual(resp.final_response.strip(), "Hey there!")

    def test_no_on_event_falls_through_to_structured_path(self):
        """Without on_event, the streaming fast path must NOT trigger; we
        verify by giving a model that has no chat_structured / no chat_stream
        and confirm we don't crash via streaming. Easier: use a model whose
        chat_stream raises if called, then ensure it's not called."""

        class _NoStreamModel:
            model_name = "no-stream"
            config: dict = {}

            async def chat_stream(self, *a, **kw):
                raise AssertionError("chat_stream should not be called when on_event is None")
                yield ""  # pragma: no cover

            async def chat_structured(self, *a, **kw):
                raise RuntimeError("structured path reached intentionally")

            def record_performance(self, *a, **kw):
                pass

        model = _NoStreamModel()
        layer = DeliberationLayer(_FakeRouter(model), soul_config={"system_prompt": "VIKI."})
        ctx = {
            "raw_input": "hi",
            "intent_type": "conversation",
            "sentiment": "neutral",
            "recommended_capabilities": ["chatter"],
            "use_lite_schema": True,
            "action_results": [],
            "use_ensemble": False,
            "on_event": None,
            "conversation_history": [],
        }
        # The structured path WILL be reached and will raise — we accept that
        # and assert chat_stream was never called by checking the exception
        # type.
        try:
            asyncio.run(layer._logic(ctx))
        except Exception as e:
            self.assertNotIn("chat_stream should not be called", str(e))


if __name__ == "__main__":
    unittest.main()

"""
Smoke test for the in-process event bus that powers /ws.
"""
from __future__ import annotations

import json
import unittest

from viki.api.events import EventBus


class TestEventBus(unittest.TestCase):
    def test_subscribe_and_publish(self):
        bus = EventBus()
        sub = bus.subscribe()
        bus.publish("ping", {"x": 1}, channel="default")
        msg = sub.queue.get_nowait()
        decoded = json.loads(msg)
        self.assertEqual(decoded["event"], "ping")
        self.assertEqual(decoded["data"]["x"], 1)

    def test_channel_filtering(self):
        bus = EventBus()
        sub = bus.subscribe(channels=["missions"])
        bus.publish("traces", {}, channel="traces")
        bus.publish("mission_created", {"id": "abc"}, channel="missions")
        msg = sub.queue.get_nowait()
        self.assertIn("mission_created", msg)
        self.assertTrue(sub.queue.empty())

    def test_unsubscribe(self):
        bus = EventBus()
        sub = bus.subscribe()
        bus.unsubscribe(sub.id)
        self.assertEqual(bus.stats()["subscribers"], 0)


if __name__ == "__main__":
    unittest.main()

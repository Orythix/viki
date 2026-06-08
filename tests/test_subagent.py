"""
Phase 4: tests for SubAgent (isolated memory, inbox/outbox, cancellation).
"""

from __future__ import annotations

import asyncio
import unittest

from core.specialist_agent import SubAgent, SubAgentManager


def _run(coro):
    return asyncio.run(coro)


class TestSubAgent(unittest.TestCase):
    def test_isolated_scratchpad(self):
        a = SubAgent(name="a")
        b = SubAgent(name="b")
        a.remember("user", "alpha")
        b.remember("user", "beta")
        self.assertEqual(len(a.scratchpad), 1)
        self.assertEqual(len(b.scratchpad), 1)
        self.assertNotEqual(a.scratchpad[0]["content"], b.scratchpad[0]["content"])

    def test_capability_scope(self):
        a = SubAgent(name="a", capabilities={"internet_research"})
        self.assertTrue(a.has_capability("internet_research"))
        self.assertFalse(a.has_capability("shell_exec"))

    def test_message_passing(self):
        async def runner(self_agent: SubAgent):
            msg = await self_agent.pull(timeout=1.0)
            assert msg is not None
            await self_agent.emit(f"echo:{msg.body}")
            return "done"

        async def go():
            agent = SubAgent(name="echo")
            agent.spawn(runner)
            await agent.send("ping")
            out = await agent.recv(timeout=1.0)
            await agent.join(timeout=1.0)
            return out, agent.result

        out, result = _run(go())
        self.assertIsNotNone(out)
        self.assertEqual(out.body, "echo:ping")
        self.assertEqual(result, "done")

    def test_cancel(self):
        async def runner(_):
            await asyncio.sleep(5)
            return "should not reach"

        async def go():
            agent = SubAgent(name="slow")
            agent.spawn(runner)
            await asyncio.sleep(0.05)
            agent.cancel()
            try:
                await agent.join(timeout=1.0)
            except Exception:
                pass
            return agent

        agent = _run(go())
        self.assertEqual(agent.error, "cancelled")
        self.assertFalse(agent.is_running)


class TestSubAgentManager(unittest.TestCase):
    def test_register_list_prune(self):
        async def runner(_):
            return "ok"

        async def go():
            mgr = SubAgentManager()
            for i in range(3):
                a = SubAgent(name=f"a{i}")
                a.spawn(runner)
                mgr.register(a)
            await asyncio.sleep(0.1)
            listed = mgr.list()
            removed = mgr.prune_finished()
            return listed, removed

        listed, removed = _run(go())
        self.assertEqual(len(listed), 3)
        self.assertGreaterEqual(removed, 1)


if __name__ == "__main__":
    unittest.main()

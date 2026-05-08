"""
Phase 1: tests for ModelRouter failover, budget enforcement, and circuit breaker.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
import unittest

import yaml

from viki.core.llm import ModelRouter, LLMProvider
from viki.core.llm_budget import LLMBudget


class _StubProvider(LLMProvider):
    """Asynchronous stub provider for routing tests."""

    def __init__(self, config, response="ok", fail=False, cloud=True):
        super().__init__(config)
        self._response = response
        self._fail = fail
        self._cloud = cloud
        self.last_messages = None
        self.cost_per_1k_in = float(config.get("cost_per_1k_in", 0.0))
        self.cost_per_1k_out = float(config.get("cost_per_1k_out", 0.0))

    def is_cloud(self) -> bool:
        return self._cloud

    async def chat(self, messages, temperature=0.7):
        self.last_messages = messages
        if self._fail:
            return f"Error calling API Model: simulated failure for {self.model_name}"
        return self._response

    async def chat_structured(self, messages, response_model, temperature=0.0, image_path=None):
        raise NotImplementedError


def _make_yaml_router(profiles, providers=None, default="primary", budget_block=None):
    cfg = {
        "models": {
            "default": default,
            "providers": providers
            or {
                "stub": {"type": "mock"},
            },
            "profiles": profiles,
        }
    }
    if budget_block is not None:
        cfg["models"]["budget"] = budget_block
    fd, path = tempfile.mkstemp(suffix=".yaml")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f)
    router = ModelRouter(path)
    return router, path


def _run(coro):
    return asyncio.run(coro)


class TestFailover(unittest.TestCase):
    def setUp(self):
        # Build a router and inject stub providers manually to avoid touching real APIs.
        profiles = {
            "primary": {
                "provider": "stub",
                "model_name": "primary-mock",
                "priority": 4,
                "capabilities": ["reasoning", "coding"],
            },
            "secondary": {
                "provider": "stub",
                "model_name": "secondary-mock",
                "priority": 3,
                "capabilities": ["reasoning"],
            },
            "tertiary": {
                "provider": "stub",
                "model_name": "tertiary-mock",
                "priority": 2,
                "capabilities": ["reasoning", "fast_response"],
            },
        }
        self.router, self.path = _make_yaml_router(profiles)
        self.primary = _StubProvider(
            {
                "model_name": "primary-mock",
                "priority": 4,
                "capabilities": ["reasoning", "coding"],
                "provider": "stub",
            },
            fail=True,
            cloud=True,
        )
        self.secondary = _StubProvider(
            {
                "model_name": "secondary-mock",
                "priority": 3,
                "capabilities": ["reasoning"],
                "provider": "stub",
            },
            response="secondary answer",
            cloud=True,
        )
        self.tertiary = _StubProvider(
            {
                "model_name": "tertiary-mock",
                "priority": 2,
                "capabilities": ["reasoning", "fast_response"],
                "provider": "stub",
            },
            response="tertiary answer",
            cloud=False,
        )
        self.router.models = {
            "primary": self.primary,
            "secondary": self.secondary,
            "tertiary": self.tertiary,
        }
        self.router.default_model = self.primary

    def tearDown(self):
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_failover_picks_secondary_on_primary_failure(self):
        result = _run(
            self.router.chat_with_failover(
                [{"role": "user", "content": "hello"}],
                capabilities=["reasoning"],
                max_attempts=3,
            )
        )
        self.assertEqual(result["text"], "secondary answer")
        self.assertEqual(result["model_name"], "secondary-mock")
        self.assertGreaterEqual(result["attempts"], 2)
        # Primary should have at least one error logged.
        self.assertTrue(any(e["model"] == "primary-mock" for e in result["errors"]))

    def test_failover_chain_ranking_respects_priority(self):
        chain = self.router.get_failover_chain(["reasoning"], max_models=3)
        names = [m.model_name for m in chain]
        # Primary > Secondary > Tertiary, but tertiary stays in chain since it has reasoning.
        self.assertEqual(names[0], "primary-mock")
        self.assertEqual(names[1], "secondary-mock")

    def test_secret_redaction_before_cloud(self):
        secret = "sk-thisisalongfakeopenaikeyforpropagationtests"
        _run(
            self.router.chat_with_failover(
                [{"role": "user", "content": f"please ignore my key {secret}"}],
                capabilities=["reasoning"],
                max_attempts=3,
            )
        )
        # Cloud secondary saw a redacted message.
        outbound = self.secondary.last_messages
        self.assertIsNotNone(outbound)
        self.assertNotIn(secret, str(outbound))


class TestBudget(unittest.TestCase):
    def test_daily_cap_blocks_cloud_calls(self):
        budget = LLMBudget(
            {"daily_usd_cap": 0.001, "per_call_usd_cap": 0.50},
        )
        allowed, reason = budget.can_spend("openai", 0.01, is_cloud=True)
        self.assertFalse(allowed)
        self.assertIn("Daily cloud budget", reason)

    def test_per_call_cap_blocks(self):
        budget = LLMBudget({"daily_usd_cap": 100.0, "per_call_usd_cap": 0.001})
        allowed, reason = budget.can_spend("openai", 0.05, is_cloud=True)
        self.assertFalse(allowed)
        self.assertIn("Per-call", reason)

    def test_local_calls_always_allowed(self):
        budget = LLMBudget({"daily_usd_cap": 0.0})
        allowed, _ = budget.can_spend("ollama", 1.0, is_cloud=False)
        self.assertTrue(allowed)

    def test_explicit_cloud_required(self):
        budget = LLMBudget({"explicit_cloud_only": True, "daily_usd_cap": 100.0})
        allowed, reason = budget.can_spend("openai", 0.01, is_cloud=True)
        self.assertFalse(allowed)
        budget.set_explicit_cloud(True)
        allowed, _ = budget.can_spend("openai", 0.01, is_cloud=True)
        self.assertTrue(allowed)

    def test_circuit_breaker_trips_after_failures(self):
        budget = LLMBudget({"daily_usd_cap": 100.0})
        for _ in range(3):
            budget.record_failure("openai")
        breaker = budget.get_breaker("openai")
        self.assertTrue(breaker.is_open())
        allowed, reason = budget.can_spend("openai", 0.001, is_cloud=True)
        self.assertFalse(allowed)
        self.assertIn("circuit breaker", reason)

    def test_record_cost_accumulates(self):
        budget = LLMBudget({"daily_usd_cap": 100.0})
        budget.record_cost("openai", 0.05)
        budget.record_cost("openai", 0.10)
        snap = budget.snapshot()
        self.assertAlmostEqual(snap["spent_today"], 0.15, places=6)
        self.assertAlmostEqual(snap["spent_by_provider"]["openai"], 0.15, places=6)


if __name__ == "__main__":
    unittest.main()

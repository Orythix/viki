"""
Phase 1: tests for cross-provider EnsembleEngine and synthesizer invocation.
"""

from __future__ import annotations

import asyncio
import unittest

from viki.core.ensemble import EnsembleEngine
from viki.core.inference_gateway import LLMProvider


class _StubProvider(LLMProvider):
    def __init__(self, name, provider_name, capabilities=None, priority=2, response_prefix=""):
        super().__init__(
            {
                "model_name": name,
                "provider": provider_name,
                "capabilities": capabilities or ["reasoning"],
                "priority": priority,
            }
        )
        self.provider_name = provider_name
        self.response_prefix = response_prefix
        self.calls: list[list[dict[str, str]]] = []

    def is_cloud(self) -> bool:
        return self.provider_name not in ("local", "lmstudio", "mock")

    async def chat(self, messages, temperature=0.7):
        self.calls.append(messages)
        last = messages[-1].get("content") if messages else ""
        return f"{self.response_prefix}: {last[:30]}"

    async def chat_structured(self, messages, response_model, temperature=0.0, image_path=None):
        raise NotImplementedError


class _StubRouter:
    def __init__(self, models):
        self.models = {m.model_name: m for m in models}

    def get_failover_chain(self, capabilities=None, max_models=8):
        scored = []
        for m in self.models.values():
            cap_match = sum(
                1 for c in (capabilities or []) if c in m.config.get("capabilities", [])
            )
            scored.append((cap_match * m.config.get("priority", 1), m))
        scored.sort(key=lambda x: -x[0])
        return [m for _, m in scored[:max_models]]

    def get_model(self, capabilities=None):
        return list(self.models.values())[0]


def _run(coro):
    return asyncio.run(coro)


class TestEnsemble(unittest.TestCase):
    def setUp(self):
        self.anthropic = _StubProvider(
            "claude-mock", "anthropic", priority=4, response_prefix="claude"
        )
        self.openai = _StubProvider("gpt-mock", "openai", priority=4, response_prefix="gpt")
        self.gemini = _StubProvider("gemini-mock", "gemini", priority=3, response_prefix="gemini")
        self.local = _StubProvider("local-mock", "local", priority=2, response_prefix="local")
        self.router = _StubRouter([self.anthropic, self.openai, self.gemini, self.local])
        self.ensemble = EnsembleEngine(self.router)

    def test_ensemble_uses_distinct_providers(self):
        trace = _run(
            self.ensemble.run_ensemble(
                "How should we structure a planner-executor agent?",
                {"narrative_identity": "VIKI"},
                selected_agents=["critic", "explorer", "aligner"],
            )
        )
        self.assertIn("critic", trace)
        self.assertIn("explorer", trace)
        self.assertIn("aligner", trace)
        self.assertIn("synthesizer", trace)
        meta = trace.get("__meta__", {})
        providers = {meta[k]["provider"] for k in ("critic", "explorer", "aligner")}
        # Should use at least two distinct providers.
        self.assertGreaterEqual(len(providers), 2)

    def test_synthesizer_runs_on_separate_call(self):
        trace = _run(
            self.ensemble.run_ensemble(
                "Plan the next refactor.",
                {},
                selected_agents=["critic", "explorer", "aligner"],
            )
        )
        self.assertTrue(isinstance(trace.get("synthesizer"), str))
        self.assertGreater(len(trace["synthesizer"]), 5)

    def test_ensemble_handles_missing_agent_gracefully(self):
        trace = _run(
            self.ensemble.run_ensemble(
                "Test",
                {},
                selected_agents=["nonexistent_agent"],
            )
        )
        self.assertEqual(trace, {})


if __name__ == "__main__":
    unittest.main()

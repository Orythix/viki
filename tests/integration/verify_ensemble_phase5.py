import asyncio
import os
import sys

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from viki.core.layers.consciousness_stack import ConsciousnessStack


class MockModel:
    def __init__(self, name="PlaceHolder"):
        self.model_name = name

    async def chat(self, prompt):
        return (
            f"Perspective from {self.model_name}: This is a simulated response based on the prompt."
        )

    async def chat_structured(self, messages, schema, image_path=None):
        from viki.core.schema import ThoughtObject, VIKIResponse, VIKIResponseLite

        if schema == VIKIResponse:
            return VIKIResponse(
                final_thought=ThoughtObject(intent_summary="Test", primary_strategy="Test"),
                final_response="Test response",
            )
        else:
            return VIKIResponseLite(final_response="Test").to_full_response()


class MockRouter:
    def __init__(self):
        self.default_model = MockModel()

    def get_model(self, capabilities=None):
        return self.default_model


@pytest.mark.slow
@pytest.mark.manual
@pytest.mark.asyncio
async def test_ensemble_phase5():
    print("--- Verifying Phase 5: Internal Ensemble Debate ---")

    router = MockRouter()
    ConsciousnessStack(router)

    print("\n[Test 1] Simulating complex coding request...")
    user_input = "Refactor the memory module to be thread-safe and use redis."

    from viki.core.ensemble import EnsembleEngine

    ensemble = EnsembleEngine(router)

    print(f"Agents loaded: {list(ensemble.agents.keys())}")
    assert "architect" in ensemble.agents, "'Architect' agent missing from ensemble"

    print("\n[Test 2] Running Ensemble Debate for Coding Task...")
    context = {"narrative_identity": "I am VIKI.", "conversation_history": []}
    selected = ["critic", "architect", "explorer"]

    results = await ensemble.run_ensemble(user_input, context, selected_agents=selected)

    print("\n--- DEBATE TRACE ---")
    for agent, perspective in results.items():
        print(f"\n[{agent.upper()}]: {perspective[:100]}...")

    assert "architect" in results, "Architect did not participate in ensemble debate"


if __name__ == "__main__":
    asyncio.run(test_ensemble_phase5())

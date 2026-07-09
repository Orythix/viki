import asyncio
import os
import sys

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from viki.core.evolution import EvolutionEngine


@pytest.mark.slow
@pytest.mark.manual
@pytest.mark.asyncio
async def test_evolution():
    print("--- Initializing VIKI Evolution Engine ---")
    data_dir = os.path.join("viki", "data", "test_evolution")
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)

    engine = EvolutionEngine(data_dir)

    print("\n--- TEST 1: PROPOSE REFLEX MUTATION ---")
    engine.propose_mutation(
        m_type="reflex",
        description="Add reflex shortcut for 'what time is it' -> time_skill",
        value={"input": "what time is it", "skill": "time_skill", "params": {}},
        pattern_id="what_time",
    )

    pending = engine.get_pending_proposals()
    print(f"Pending Proposals: {len(pending)}")

    print("\n--- TEST 2: SIMULATE SUCCESS STREAK ---")
    engine.record_success("what_time")
    engine.record_success("what_time")
    print("Recording 3rd success...")
    engine.record_success("what_time")

    applied = engine.get_active_mutations("reflex")
    print(f"Applied Reflex Mutations: {len(applied)}")
    if applied:
        print(f"Applied: {applied[0]['description']}")

    print("\n--- TEST 3: PROPOSE PRIORITY WEIGHTING ---")
    engine.propose_mutation(
        m_type="priority",
        description="Increase curiosity weighting due to research success",
        value={"curiosity": 0.15},
    )

    weights = engine.get_agent_weightings()
    print(f"Weights before manual approval: {weights}")

    pending = engine.get_pending_proposals()
    if pending:
        m_id = pending[0]["id"]
        print(f"Approving {m_id} manually...")
        engine.approve_mutation(m_id)

        new_weights = engine.get_agent_weightings()
        print(f"Weights after approval: {new_weights}")

    print("\n[VERIFICATION COMPLETE]")


if __name__ == "__main__":
    asyncio.run(test_evolution())

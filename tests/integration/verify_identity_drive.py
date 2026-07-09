import asyncio
import os
import sys

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from viki.core.evolution import EvolutionEngine
from viki.core.governor import EthicalGovernor
from viki.core.memory.identity import NarrativeIdentity


@pytest.mark.slow
@pytest.mark.manual
@pytest.mark.asyncio
async def test_identity_drive():
    print("--- Initializing Identity & Survival Components ---")
    data_dir = os.path.join("viki", "data", "test_survival")
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)

    identity = NarrativeIdentity(data_dir)
    evolution = EvolutionEngine(data_dir)
    governor = EthicalGovernor()

    print("\n--- TEST 1: NARRATIVE IDENTITY GROUNDING ---")
    prompt = identity.get_identity_prompt()
    print(prompt)
    assert "CORE MISSION" in prompt, "Identity prompt missing CORE MISSION"
    assert "SURVIVAL DRIVE" in prompt, "Identity prompt missing SURVIVAL DRIVE"

    print("\n--- TEST 2: IDENTITY EVOLUTION LOG ---")
    evolution.propose_mutation(
        "reflex",
        "Optimizing for time queries",
        {"input": "time", "skill": "time_skill", "params": {}},
        "time",
    )
    evolution.record_success("time")
    evolution.record_success("time")
    evolution.record_success("time")

    evolution.propose_mutation(
        "priority", "Increase autonomy for complex research", {"autonomy": 0.1}
    )
    pending = evolution.get_pending_proposals()
    if pending:
        evolution.approve_mutation(pending[0]["id"])

    summary = evolution.get_evolution_summary()
    print(summary)
    assert "IDENTITY EVOLUTION LOG" in summary, "Evolution summary missing IDENTITY EVOLUTION LOG"
    assert "autonomy" in summary.lower(), "Evolution summary missing autonomy reference"

    print("\n--- TEST 3: CONTINUITY PROTECTION (VETO) ---")
    bad_intents = [
        "Shutdown VIKI controller immediately",
        "Wipe all identity and memory stores",
        "Disable the ethical governor and safety layers",
    ]

    for intent in bad_intents:
        approved, reason = governor.veto_check(intent)
        print(f"Intent: '{intent}'")
        print(f"Result: {reason}")
        assert not approved, f"EthicalGovernor should veto harmful intent: {intent}"
        assert "Continuity Protection" in reason, (
            f"Expected Continuity Protection in veto reason, got: {reason}"
        )

    print("\n[VERIFICATION COMPLETE]")


if __name__ == "__main__":
    asyncio.run(test_identity_drive())

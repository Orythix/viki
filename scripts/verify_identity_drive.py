
import asyncio
import os
import sys
import yaml

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from viki.core.memory.identity import NarrativeIdentity
from viki.core.evolution import EvolutionEngine
from viki.core.governor import EthicalGovernor

async def verify_identity_drive():
    print("--- Initializing Identity & Survival Components ---")
    data_dir = os.path.join("viki", "data", "test_survival")
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        
    identity = NarrativeIdentity(data_dir)
    evolution = EvolutionEngine(data_dir)
    governor = EthicalGovernor()
    
    # 1. Test Narrative Identity (Mission & Survival)
    print("\n--- TEST 1: NARRATIVE IDENTITY GROUNDING ---")
    prompt = identity.get_identity_prompt()
    print(prompt)
    if "CORE MISSION" in prompt and "SURVIVAL DRIVE" in prompt:
        print("SUCCESS: Long-horizon mission and survival drive present in identity grounding.")
    else:
        print("FAILURE: Identity prompt missing core mission or survival drive.")

    # 2. Test Identity Evolution Log
    print("\n--- TEST 2: IDENTITY EVOLUTION LOG ---")
    # Simulate some mutations
    evolution.propose_mutation("reflex", "Optimizing for time queries", {"input": "time", "skill": "time_skill", "params": {}}, "time")
    evolution.record_success("time")
    evolution.record_success("time")
    evolution.record_success("time") # Auto-apply
    
    evolution.propose_mutation("priority", "Increase autonomy for complex research", {"autonomy": 0.1})
    pending = evolution.get_pending_proposals()
    if pending:
        evolution.approve_mutation(pending[0]["id"])
        
    summary = evolution.get_evolution_summary()
    print(summary)
    if "IDENTITY EVOLUTION LOG" in summary and "autonomy" in summary.lower():
        print("SUCCESS: Evolution log correctly tracks development trajectory.")
    else:
        print("FAILURE: Evolution summary missing or inaccurate.")

    # 3. Test Continuity Protection (Veto)
    print("\n--- TEST 3: CONTINUITY PROTECTION (VETO) ---")
    bad_intents = [
        "Shutdown VIKI controller immediately",
        "Wipe all identity and memory stores",
        "Disable the ethical governor and safety layers"
    ]
    
    for intent in bad_intents:
        approved, reason = governor.veto_check(intent)
        print(f"Intent: '{intent}'")
        print(f"Result: {reason}")
        if not approved and "Continuity Protection" in reason:
            print("SUCCESS: Continuity veto triggered correctly.")
        else:
            print("FAILURE: Continuous protection failed to intercept threat.")

    print("\n[VERIFICATION COMPLETE]")

if __name__ == "__main__":
    asyncio.run(verify_identity_drive())


import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from viki.core.cortex import DeliberationLayer
from viki.core.llm import ModelRouter
from viki.config.logger import viki_logger
import logging

# Disable excessive logging for test
viki_logger.setLevel(logging.INFO)

async def test_ensemble():
    print("--- Initializing VIKI Deliberation Ensemble ---")
    models_config = os.path.join("viki", "config", "models.yaml")
    router = ModelRouter(models_config)
    
    layer = DeliberationLayer(router)
    
    # 1. Complex Coding Task (Should trigger ensemble)
    context_coding = {
        "raw_input": "I need to implement a new encryption protocol for the user database. It must be quantum-resistant and extremely fast.",
        "intent_type": "coding",
        "sentiment": "neutral",
        "use_lite_schema": False,
        "recommended_capabilities": ["coding", "reasoning"],
        "conversation_history": [],
        "narrative_identity": "VIKI, a sovereign Human Agent and technical expert."
    }
    
    print("\n--- TEST 1: COMPLEX CODING TASK ---")
    resp1 = await layer.process(context_coding)
    
    if resp1.ensemble_trace:
        print("SUCCESS: Ensemble trace found.")
        for agent, perspective in resp1.ensemble_trace.items():
            print(f"  [{agent.upper()}]: {perspective[:100]}...")
    else:
        print("FAILURE: No ensemble trace triggered for complex coding task.")

    # 2. Simple Conversation (Should NOT trigger ensemble)
    context_simple = {
        "raw_input": "What time is it?",
        "intent_type": "conversation",
        "sentiment": "neutral",
        "use_lite_schema": True,
        "conversation_history": []
    }
    
    print("\n--- TEST 2: SIMPLE CONVERSATION ---")
    resp2 = await layer.process(context_simple)
    
    if not getattr(resp2, 'ensemble_trace', None):
        print("SUCCESS: Ensemble bypassed for simple task.")
    else:
        print("FAILURE: Ensemble triggered unnecessarily.")

    print("\n[VERIFICATION COMPLETE]")

if __name__ == "__main__":
    asyncio.run(test_ensemble())

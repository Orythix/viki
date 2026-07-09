import asyncio
import os
import sys

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

import logging

from viki.core.cortex import DeliberationLayer
from viki.core.llm import ModelRouter

from viki.config.logger import viki_logger

viki_logger.setLevel(logging.INFO)


@pytest.mark.slow
@pytest.mark.manual
@pytest.mark.asyncio
async def test_ensemble():
    print("--- Initializing VIKI Deliberation Ensemble ---")
    models_config = os.path.join("viki", "config", "models.yaml")
    router = ModelRouter(models_config)

    layer = DeliberationLayer(router)

    context_coding = {
        "raw_input": "I need to implement a new encryption protocol for the user database. It must be quantum-resistant and extremely fast.",
        "intent_type": "coding",
        "sentiment": "neutral",
        "use_lite_schema": False,
        "recommended_capabilities": ["coding", "reasoning"],
        "conversation_history": [],
        "narrative_identity": "VIKI, a sovereign Human Agent and technical expert.",
    }

    print("\n--- TEST 1: COMPLEX CODING TASK ---")
    resp1 = await layer.process(context_coding)

    if resp1.ensemble_trace:
        print("SUCCESS: Ensemble trace found.")
        for agent, perspective in resp1.ensemble_trace.items():
            print(f"  [{agent.upper()}]: {perspective[:100]}...")
    else:
        print("FAILURE: No ensemble trace triggered for complex coding task.")

    context_simple = {
        "raw_input": "What time is it?",
        "intent_type": "conversation",
        "sentiment": "neutral",
        "use_lite_schema": True,
        "conversation_history": [],
    }

    print("\n--- TEST 2: SIMPLE CONVERSATION ---")
    resp2 = await layer.process(context_simple)

    if not getattr(resp2, "ensemble_trace", None):
        print("SUCCESS: Ensemble bypassed for simple task.")
    else:
        print("FAILURE: Ensemble triggered unnecessarily.")

    print("\n[VERIFICATION COMPLETE]")


if __name__ == "__main__":
    asyncio.run(test_ensemble())

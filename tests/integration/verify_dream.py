import asyncio
import os
import sys

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from viki.core.llm import ModelRouter

from viki.core.memory.narrative import NarrativeMemory


@pytest.mark.slow
@pytest.mark.manual
@pytest.mark.asyncio
async def test_dream():
    print("--- Initializing Narrative Dream Cycle ---")
    data_dir = os.path.join("viki", "data", "test_dream")
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)

    root_dir = os.path.join(os.path.dirname(__file__), "..", "..")
    models_conf = os.path.join(root_dir, "./config/models.yaml")
    router = ModelRouter(models_conf)

    memory = NarrativeMemory(data_dir)

    print("\n--- TEST 1: SEEDING EPISODES ---")
    episodes = [
        (
            "User asked for file search",
            "Search for 'config.yaml'",
            {},
            "find_file",
            "Found at viki/config/config.yaml",
            0.9,
        ),
        (
            "User corrected my import",
            "Fix import in evolution.py",
            {},
            "edit_file",
            "Import corrected to viki.core.llm",
            0.95,
        ),
        (
            "User wants Python for everything",
            "Write script for data cleaning",
            {},
            "write_file",
            "Python script created",
            0.85,
        ),
        (
            "User expressed frustration with UI",
            "Fix CSS alignment",
            {},
            "edit_file",
            "Alignment fixed in index.css",
            0.7,
        ),
        (
            "User requested a specialized skill",
            "Create Git control skill",
            {},
            "neural_forge",
            "Synthesis started",
            0.9,
        ),
    ]

    for ctx, intent, plan, action, outcome, conf in episodes:
        memory.add_episode(ctx, intent, plan, action, outcome, conf)

    cur = memory.conn.cursor()
    cur.execute("UPDATE episodes SET access_count = 1")
    memory.conn.commit()

    print("\n--- TEST 2: TRIGGERING DREAM CYCLE ---")
    try:
        await memory.consolidate(router)
    except Exception as e:
        print(f"Dream cycle call failed (expected if no API key): {e}")

    print("\n--- TEST 3: RETRIEVING WISDOM ---")
    wisdom = memory.get_semantic_knowledge()
    if wisdom:
        print(f"SUCCESS: {len(wisdom)} insights consolidated into Semantic Wisdom.")
        for w in wisdom:
            print(f"- [{w['category'].upper()}]: {w['insight']}")
    else:
        print(
            "FAILURE/PENDING: No wisdom extracted. This could be due to API failure or LLM output format."
        )

    print("\n[VERIFICATION COMPLETE]")


if __name__ == "__main__":
    asyncio.run(test_dream())

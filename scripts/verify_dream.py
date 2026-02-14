
import asyncio
import os
import sys
import yaml

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from viki.core.memory.narrative import NarrativeMemory
from viki.core.llm import ModelRouter

async def verify_dream():
    print("--- Initializing Narrative Dream Cycle ---")
    data_dir = os.path.join("viki", "data", "test_dream")
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    models_conf = os.path.join(root_dir, "viki/config/models.yaml")
    router = ModelRouter(models_conf)
    
    memory = NarrativeMemory(data_dir)
    
    # 1. Seed Fake Episodes
    print("\n--- TEST 1: SEEDING EPISODES ---")
    episodes = [
        ("User asked for file search", "Search for 'config.yaml'", {}, "find_file", "Found at viki/config/config.yaml", 0.9),
        ("User corrected my import", "Fix import in evolution.py", {}, "edit_file", "Import corrected to viki.core.llm", 0.95),
        ("User wants Python for everything", "Write script for data cleaning", {}, "write_file", "Python script created", 0.85),
        ("User expressed frustration with UI", "Fix CSS alignment", {}, "edit_file", "Alignment fixed in index.css", 0.7),
        ("User requested a specialized skill", "Create Git control skill", {}, "neural_forge", "Synthesis started", 0.9)
    ]
    
    for ctx, intent, plan, action, outcome, conf in episodes:
        memory.add_episode(ctx, intent, plan, action, outcome, conf)
    
    # Mark them as accessed so they are consolidated
    cur = memory.conn.cursor()
    cur.execute("UPDATE episodes SET access_count = 1")
    memory.conn.commit()
    
    # 2. Trigger Dream Cycle
    print("\n--- TEST 2: TRIGGERING DREAM CYCLE ---")
    # Note: This will call the real LLM. If no API key, it might fail.
    # For verification, we'll try it.
    try:
        await memory.consolidate(router)
    except Exception as e:
        print(f"Dream cycle call failed (expected if no API key): {e}")

    # 3. Check for Semantic Wisdom
    print("\n--- TEST 3: RETRIEVING WISDOM ---")
    wisdom = memory.get_semantic_knowledge()
    if wisdom:
        print(f"SUCCESS: {len(wisdom)} insights consolidated into Semantic Wisdom.")
        for w in wisdom:
            print(f"- [{w['category'].upper()}]: {w['insight']}")
    else:
        print("FAILURE/PENDING: No wisdom extracted. This could be due to API failure or LLM output format.")

    print("\n[VERIFICATION COMPLETE]")

if __name__ == "__main__":
    asyncio.run(verify_dream())

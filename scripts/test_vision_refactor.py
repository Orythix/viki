
import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from viki.core.controller import VIKIController
from viki.config.logger import viki_logger
import logging

# Set logging to see thought process
logging.basicConfig(level=logging.INFO)
viki_logger.setLevel(logging.INFO)

async def run_vision_refactor_test():
    print("--- FULL SYSTEM TEST: Vision + Architect + Refactoring ---")
    
    # 1. Setup Controller
    config_path = os.path.join("viki", "config", "settings.yaml")
    soul_path = os.path.join("viki", "data", "soul.yaml")
    viki = VIKIController(config_path, soul_path)
    
    # 2. Create a dummy 'legacy' file to maximize the Architect effect
    legacy_file = "viki/skills/builtins/legacy_math.py"
    with open(legacy_file, 'w') as f:
        f.write("# LEGACY MONOLITHIC CODE\n")
        f.write("def do_math(op, a, b):\n")
        f.write("    if op == 'add': return a + b\n")
        f.write("    if op == 'sub': return a - b\n")
        f.write("    print('doing math')\n")
        f.write("    # TODO: Refactor this mess\n")
        f.write("    return 0\n")
    
    print(f"Created legacy file: {legacy_file}")
    
    # 3. Simulate Multi-Modal Request
    # We pretend the user sent an image path (or VIKI took a screenshot of code)
    # Here we just instruct her to *read* the file content as if she saw it.
    # To test vision specifically, we'd need an actual image. 
    # For this test, we'll verify the COGNITIVE LOOP:
    # Vision (Concept) -> Architect (Plan) -> Refactor (Action)
    
    request = (
        f"I'm looking at {legacy_file}. "
        "It's a mess. Please analyze it and refactor it into a proper class-based structure. "
        "Use your Architect persona to design it."
    )
    
    print(f"\nUser Request: '{request}'\n")
    
    # 4. Stream Thoughts
    def on_event(event_type, data):
        if event_type == "thought":
            print(f"\n[THOUGHT]: {data}")
        elif event_type == "status":
            print(f"[STATUS]: {data}")
            
    response = await viki.process_request(request, on_event=on_event)
    
    print("\n--- FINAL RESPONSE ---\n")
    print(response)

if __name__ == "__main__":
    asyncio.run(run_vision_refactor_test())

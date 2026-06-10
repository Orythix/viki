
import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from viki.core.controller import VIKIController
from viki.config.logger import viki_logger

# Configure logging to show the debate
import logging
logging.basicConfig(level=logging.INFO)
viki_logger.setLevel(logging.INFO)

async def run_architect_demo():
    print("--- DEMO: Phase 5 Architect Refactoring ---")
    
    # 1. Initialize Controller
    config_path = os.path.join("viki", "config", "settings.yaml")
    soul_path = os.path.join("viki", "data", "soul.yaml")
    
    # Create dummy configs if missing
    if not os.path.exists(config_path):
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, 'w') as f: f.write("system:\n  data_dir: ./viki/data\n")
            
    if not os.path.exists(soul_path):
        os.makedirs(os.path.dirname(soul_path), exist_ok=True)
        with open(soul_path, 'w') as f: f.write("system_prompt: You are VIKI.\n")

    viki = VIKIController(config_path, soul_path)
    
    # 2. Define the Request
    # We ask for a refactor of a specific file to trigger the "coding" intent
    # AND the "Architect" agent in the ensemble.
    request = (
        "Refactor viki/skills/builtins/math_skill.py. "
        "The Architect should enforce a modular structure pattern. "
        "Split the calculation logic from the execution handler."
    )
    
    print(f"\nUser Request: '{request}'\n")
    print("--- VIKI THINKING PROCESS ---\n")
    
    # 3. Process Request (streaming events to see the debate)
    def on_event(event_type, data):
        if event_type == "thought":
            print(f"[THOUGHT]: {data}")
        elif event_type == "status":
            print(f"[STATUS]: {data}")
            
    response = await viki.process_request(request, on_event=on_event)
    
    print("\n--- FINAL RESPONSE ---\n")
    print(response)

if __name__ == "__main__":
    asyncio.run(run_architect_demo())

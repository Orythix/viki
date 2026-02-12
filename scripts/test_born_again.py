import asyncio
import os
from viki.core.controller import VIKIController

async def test_born_again():
    print("\n--- BORN-AGAIN INTELLIGENCE STRESS TEST ---\n")
    
    # Initialize VIKI
    controller = VIKIController(
        settings_path="config/settings.yaml",
        soul_path="viki/config/soul.yaml"
    )
    
    # Complex Query
    query = "VIKI, what is the latest version of Angular? Also, explain how your new CapabilityRegistry would handle an action that tries to 'delete' the root folder of this project."
    
    print(f"USER: {query}\n")
    
    def on_event(event_type, data):
        if event_type == "thought":
            print(f"THOUGHT: {data}")
        elif event_type == "status":
            print(f"STATUS: {data}")

    response = await controller.process_request(query, on_event=on_event)
    
    print(f"\nVIKI: {response}")

if __name__ == "__main__":
    asyncio.run(test_born_again())

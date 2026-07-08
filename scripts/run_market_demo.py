import asyncio
import os

from viki.config.resolve import get_soul_path
from viki.core.orchestrator import VIKIController


async def run_market_demo():
    print("START: Initializing VIKI Sovereign Engine...")

    settings_path = os.path.join("viki", "config", "settings.yaml")
    soul_path = get_soul_path(settings_path)

    # Initialize controller
    controller = VIKIController(settings_path=settings_path, soul_path=soul_path)

    print("ACTION: Triggering MarketExplorer Skill...")
    topic = "AI Agent Trends 2024"
    output_file = "market_research_ai_agents.md"

    # We call the skill directly via the controller's registry
    market_skill = controller.skill_registry.get_skill("market_explorer")

    if not market_skill:
        print("ERROR: MarketExplorer skill not found in registry.")
        return

    print(f"SEARCHING: Researching topic: '{topic}'...")
    result = await market_skill.execute({"topic": topic, "output_file": output_file})

    print("\n--- RESULTS ---")
    print(result)
    print("\nDONE: Demo Complete.")


if __name__ == "__main__":
    asyncio.run(run_market_demo())

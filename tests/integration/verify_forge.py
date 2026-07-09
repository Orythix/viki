import asyncio
import os
import sys

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from viki.core.llm import ModelRouter

from viki.core.evolution import EvolutionEngine
from viki.skills.registry import SkillRegistry


@pytest.mark.slow
@pytest.mark.manual
@pytest.mark.asyncio
async def test_forge():
    print("--- Initializing Neural Forge v2 ---")
    data_dir = os.path.join("viki", "data", "test_forge")
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)

    root_dir = os.path.join(os.path.dirname(__file__), "..", "..")
    models_conf = os.path.join(root_dir, "./config/models.yaml")
    router = ModelRouter(models_conf)

    registry = SkillRegistry()
    evolution = EvolutionEngine(data_dir)
    evolution.set_model_router(router)
    evolution.set_skill_registry(registry)

    print("\n--- TEST 1: SKILL SYNTHESIS (FORGE) ---")
    task = "A skill that returns the current system platform and python version"

    mock_code = """
import sys
import platform
from viki.skills.base import BaseSkill
from typing import Dict, Any

class PlatformInfoSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "platform_info"

    @property
    def description(self) -> str:
        return \"Returns system platform and python version.\"

    async def execute(self, params: Dict[str, Any]) -> str:
        return f"System: {platform.system()} {platform.release()} | Python: {sys.version}"
"""
    mutation = evolution.propose_mutation(
        m_type="skill_synthesis",
        description=f"Neural Forge: New skill 'platform_info' for {task}",
        value={"code": mock_code, "skill_name": "platform_info"},
    )

    if mutation and "code" in mutation["value"]:
        print(f"SUCCESS: Skill synthesized. Name: {mutation['value']['skill_name']}")
        print("Generated Code Snippet:")
        print(mutation["value"]["code"][:200] + "...")

        print("\n--- TEST 2: APPROVAL & HOT-LOADING ---")
        evolution.approve_mutation(mutation["id"])

        skill_name = mutation["value"]["skill_name"]
        if skill_name in registry.skills:
            print(f"SUCCESS: Skill '{skill_name}' hot-loaded into registry.")
            print("\n--- TEST 3: EXECUTION ---")
            skill = registry.get_skill(skill_name)
            result = await skill.execute({})
            print(f"Execution Result: {result}")
            if "Python" in result:
                print("SUCCESS: Synthesized skill executed correctly.")
            else:
                print("FAILURE: Synthesized skill execution failed or returned unexpected result.")
        else:
            print(f"FAILURE: Skill '{skill_name}' NOT found in registry after approval.")
    else:
        print("FAILURE: Skill synthesis failed.")

    print("\n[VERIFICATION COMPLETE]")


if __name__ == "__main__":
    asyncio.run(test_forge())

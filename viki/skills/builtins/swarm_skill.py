import asyncio
from typing import Dict, Any, List
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger
from viki.core.llm import StructuredPrompt

class SwarmSkill(BaseSkill):
    """
    Sub-Agent Swarm (The Council).
    Spawns specialized worker agents to solve complex problems.
    """
    def __init__(self, controller):
        self.controller = controller
        self._name = "swarm_council"
        self._description = "Spawn a council of specialized agents for tasks like specs, research, or reviews. Usage: swarm_council(objective='...') "

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "objective": {
                    "type": "string",
                    "description": "The complex objective for the council to solve (e.g. 'design a secure login system')."
                }
            },
            "required": ["objective"]
        }

    async def execute(self, params: Dict[str, Any]) -> str:
        objective = params.get("objective")
        if not objective: return "Error: No objective provided."

        viki_logger.info(f"Swarm: Convoking the council for '{objective}'")
        
        # 1. Spawn Workers (asynchronous tasks)
        workers = [
            self._spawn_worker("Researcher", objective),
            self._spawn_worker("Architect", objective),
            self._spawn_worker("Critic", objective)
        ]
        
        results = await asyncio.gather(*workers)
        
        # 2. Synthesize Results
        synthesis_prompt = [
            {"role": "system", "content": "You are VIKI Manager. Compile the following worker reports into a final comprehensive master spec/report for the creator."},
            {"role": "user", "content": f"Objective: {objective}\n\nREPORTS:\n" + "\n---\n".join(results)}
        ]
        
        model = self.controller.model_router.get_model(capabilities=["reasoning"])
        final_report = await model.chat(synthesis_prompt)
        
        return f"CONSOLIDATED COUNCIL REPORT:\n\n{final_report}"

    async def _spawn_worker(self, persona: str, objective: str) -> str:
        """Helper to call LLM with a specific worker profile."""
        sys_prompts = {
            "Researcher": "You are Worker A (Researcher). Find facts and similar cases for this objective.",
            "Architect": "You are Worker B (Architect). Define the structure and logic for this objective.",
            "Critic": "You are Worker C (Critic). Review findings and structure for potential flaws or gaps."
        }
        
        messages = [
            {"role": "system", "content": sys_prompts.get(persona, "You are a specialized worker.")},
            {"role": "user", "content": objective}
        ]
        
        # Pick a model for the worker (could be faster ones like phi3)
        model = self.controller.model_router.get_model(capabilities=["fast_response"])
        return f"[{persona} REPORT]\n" + await model.chat(messages)

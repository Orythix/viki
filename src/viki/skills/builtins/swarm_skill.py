from typing import Dict, Any, List
import asyncio
from skills.base import BaseSkill
from application.services.swarm_orchestrator import SwarmOrchestrator
from domain.entities.swarm import AgentStatus
from config.logger import viki_logger

class SwarmSkill(BaseSkill):
    """
    Sub-Agent Swarm (The Council).
    Delegates specialized tasks to sub-agents managed by the SwarmOrchestrator.
    """
    def __init__(self, orchestrator: SwarmOrchestrator, controller):
        self._orchestrator = orchestrator
        self.controller = controller

    @property
    def name(self) -> str:
        return "swarm_control"

    @property
    def description(self) -> str:
        return (
            "Delegates specialized tasks to a council of sub-agents (Researcher, Architect, Critic). "
            "Use this for parallel research, complex design problems, or multi-perspective reviews."
        )

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["delegate_council", "status", "terminate"],
                    "description": "Action to perform in the swarm."
                },
                "objective": {
                    "type": "string",
                    "description": "The complex objective for the council to solve (required for 'delegate_council')."
                },
                "agent_id": {
                    "type": "string",
                    "description": "Specific agent ID (required for 'status' or 'terminate')."
                }
            },
            "required": ["action"]
        }

    @property
    def safety_tier(self) -> str:
        return "medium"

    async def execute(self, params: Dict[str, Any]) -> str:
        action = params.get("action")
        
        if action == "delegate_council":
            objective = params.get("objective")
            if not objective:
                return "Error: No objective provided for the council."
            
            viki_logger.info(f"Swarm: Convoking the council for '{objective}'")
            
            # 1. Provision Agents and Delegate Tasks
            specialties = ["research", "coder", "reviewer"]
            workers = []
            
            for specialty in specialties:
                task = await self._orchestrator.delegate_task(f"{specialty} analysis for: {objective}", specialty)
                workers.append(self._execute_worker(task, specialty, objective))
            
            results = await asyncio.gather(*workers)
            
            # 2. Synthesize Results using the main controller's reasoning model
            synthesis_prompt = [
                {"role": "system", "content": "You are VIKI Manager. Compile the following worker reports into a final comprehensive master spec/report for the creator."},
                {"role": "user", "content": f"Objective: {objective}\n\nREPORTS:\n" + "\n---\n".join(results)}
            ]
            
            model = self.controller.model_router.get_model(capabilities=["reasoning"])
            final_report = await model.chat(synthesis_prompt)
            
            return f"CONSOLIDATED COUNCIL REPORT:\n\n{final_report}"

        elif action == "status":
            status = self._orchestrator.get_swarm_status()
            return f"Swarm Status: {status}"

        elif action == "terminate":
            agent_id = params.get("agent_id")
            if not agent_id:
                return "Error: Agent ID is required for termination."
            self._orchestrator.agent_pool.release_agent(agent_id)
            return f"Agent {agent_id} has been released."

        return f"Unknown swarm action: {action}"

    async def _execute_worker(self, task, specialty: str, objective: str) -> str:
        """Execute a specialized worker agent (simulated via LLM for now)."""
        sys_prompts = {
            "research": "You are the Researcher Agent. Find facts and similar cases for this objective.",
            "coder": "You are the Architect Agent. Define the structure and logic for this objective.",
            "reviewer": "You are the Critic Agent. Review findings and structure for potential flaws or gaps."
        }
        
        messages = [
            {"role": "system", "content": sys_prompts.get(specialty, "You are a specialized worker.")},
            {"role": "user", "content": objective}
        ]
        
        model = self.controller.model_router.get_model(capabilities=["fast_response"])
        report = await model.chat(messages)
        
        # Mark task as completed in orchestrator
        task.status = "completed"
        task.result = report
        self._orchestrator.agent_pool.release_agent(task.assigned_to)
        
        return f"[{specialty.upper()} REPORT]\n{report}"

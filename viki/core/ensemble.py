import asyncio
from typing import List, Dict, Any, Optional
from viki.config.logger import viki_logger

class EnsembleAgent:
    def __init__(self, name: str, role: str, instruction: str):
        self.name = name
        self.role = role
        self.instruction = instruction

class EnsembleEngine:
    """
    Internal Specialist Ensemble (v24)
    Handles lightweight multi-agent thinking for complex or high-risk tasks.
    """
    def __init__(self, model_router):
        self.model_router = model_router
        self.agents = {
            "critic": EnsembleAgent("Critic", "Flaw Detection", "Ruthlessly find flaws, edge cases, and logical fallacies in the current plan or response. Be precise and skeptical."),
            "explorer": EnsembleAgent("Explorer", "Creative Alternatives", "Generate creative alternatives, novel angles, and unexpected solutions. Think outside the box."),
            "aligner": EnsembleAgent("Aligner", "Ethical & Identity Alignment", "Check the plan against the Ethical Governor, core directives, and Narrative Identity. Ensure continuity and safety."),
            "synthesizer": EnsembleAgent("Synthesizer", "Integration", "Integrate the perspectives from the Critic, Explorer, and Aligner into a single, cohesive, and superior response. Resolve contradictions."),
            "architect": EnsembleAgent("Architect", "System Design & Structure", "Analyze the request from a software architecture perspective. Focus on modularity, scalability, and clean code principles. Identify potential technical debt.")
        }

    async def run_ensemble(self, user_input: str, context: Dict[str, Any], selected_agents: List[str] = None) -> Dict[str, str]:
        """
        Runs the specialist ensemble debate.
        Does NOT make external tool calls.
        """
        if not selected_agents:
            # Default ensemble for complex tasks
            selected_agents = ["critic", "explorer", "aligner"]
        
        viki_logger.info(f"Ensemble: Spinning up experts: {', '.join(selected_agents)}")
        
        # 1. Gather parallel perspectives
        tasks = []
        for agent_id in selected_agents:
            if agent_id in self.agents:
                tasks.append(self._get_perspective(agent_id, user_input, context))
        
        results = await asyncio.gather(*tasks)
        debate_trace = {selected_agents[i]: results[i] for i in range(len(results))}
        
        # 2. Integrate perspectives using the Synthesizer
        # We don't call _synthesize here because the DeliberationLayer might want to use the trace directly or in its final prompt.
        # But for "boxed" behavior, a synthesis step is good.
        
        viki_logger.debug("Ensemble: Perspectives gathered. Synthesizing...")
        return debate_trace

    async def _get_perspective(self, agent_id: str, user_input: str, context: Dict[str, Any]) -> str:
        agent = self.agents[agent_id]
        # Use a faster model for sub-agents if available
        model = self.model_router.get_model(capabilities=["reasoning", "fast_response"])
        
        # Extract grounding context
        identity = context.get("narrative_identity", "A helpful AI assistant.")
        history = str(context.get("conversation_history", []))[-1000:]
        
        prompt = (
            f"SYSTEM: You are the {agent.name} module in VIKI's internal ensemble.\n"
            f"ROLE: {agent.role}\n"
            f"INSTRUCTION: {agent.instruction}\n\n"
            f"IDENTITY GROUNDING:\n{identity}\n\n"
            f"USER INPUT: {user_input}\n"
            f"HISTORICAL CONTEXT: {history}\n\n"
            f"Provide your brief perspective (max 100 words):"
        )
        
        try:
            resp = await model.chat(prompt)
            # Strip common prefixes
            resp = resp.replace(f"{agent.name}:", "").strip()
            return resp
        except Exception as e:
            viki_logger.error(f"Ensemble Agent {agent_id} failed: {e}")
            return "Unable to generate perspective."

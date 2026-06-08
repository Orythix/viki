"""
Phase 1: Cross-provider Ensemble Engine.

Each persona binds to a *different* provider when possible, drawn from the
ModelRouter's failover chain. The synthesizer (previously declared but never
invoked) now produces the final integrated perspective from the three other
agents' outputs and returns it under the `synthesizer` key in the trace.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from config.logger import viki_logger


class EnsembleAgent:
    def __init__(
        self,
        name: str,
        role: str,
        instruction: str,
        preferred_capabilities: Optional[List[str]] = None,
        provider_hint: Optional[str] = None,
    ):
        self.name = name
        self.role = role
        self.instruction = instruction
        self.preferred_capabilities = preferred_capabilities or [
            "reasoning",
            "fast_response",
        ]
        self.provider_hint = provider_hint  # e.g. "anthropic", "openai", "gemini", "local"


class EnsembleEngine:
    """
    Cross-provider Internal Specialist Ensemble (v25).

    Differences from earlier v24:
    - Each agent attempts to bind to a different provider (provider diversity).
    - The Synthesizer is actually called and its output returned in the trace.
    - The trace records which model+provider answered each persona slot.
    """

    def __init__(self, model_router):
        self.model_router = model_router
        self.agents: Dict[str, EnsembleAgent] = {
            "critic": EnsembleAgent(
                name="Critic",
                role="Flaw Detection",
                instruction="Ruthlessly find flaws, edge cases, and logical fallacies in the current plan or response. Be precise and skeptical.",
                preferred_capabilities=["reasoning", "analysis"],
                provider_hint="anthropic",
            ),
            "explorer": EnsembleAgent(
                name="Explorer",
                role="Creative Alternatives",
                instruction="Generate creative alternatives, novel angles, and unexpected solutions. Think outside the box.",
                preferred_capabilities=["reasoning", "intelligence"],
                provider_hint="gemini",
            ),
            "aligner": EnsembleAgent(
                name="Aligner",
                role="Ethical & Identity Alignment",
                instruction="Check the plan against the Ethical Governor, core directives, and Narrative Identity. Ensure continuity and safety.",
                preferred_capabilities=["reasoning"],
                provider_hint="local",
            ),
            "synthesizer": EnsembleAgent(
                name="Synthesizer",
                role="Integration",
                instruction="Integrate the perspectives from the Critic, Explorer, and Aligner into a single, cohesive, and superior response. Resolve contradictions.",
                preferred_capabilities=["reasoning", "complex_task"],
                provider_hint="openai",
            ),
            "architect": EnsembleAgent(
                name="Architect",
                role="System Design & Structure",
                instruction="Analyze the request from a software architecture perspective. Focus on modularity, scalability, and clean code principles. Identify potential technical debt.",
                preferred_capabilities=["coding", "reasoning"],
                provider_hint="anthropic",
            ),
        }

    async def run_ensemble(
        self,
        user_input: str,
        context: Dict[str, Any],
        selected_agents: Optional[List[str]] = None,
    ) -> Dict[str, str]:
        if not selected_agents:
            selected_agents = ["critic", "explorer", "aligner"]

        selected_agents = [a for a in selected_agents if a in self.agents]
        if not selected_agents:
            return {}

        viki_logger.info("Ensemble: Running cross-provider perspectives: %s", ", ".join(selected_agents))

        used_providers: List[str] = []
        debate_trace: Dict[str, str] = {}
        meta_trace: Dict[str, Dict[str, str]] = {}

        async def _run_one(agent_id: str) -> None:
            agent = self.agents[agent_id]
            model = self._pick_model_for_agent(agent, used_providers)
            provider = getattr(model, "provider_name", "unknown")
            used_providers.append(provider)
            text = await self._invoke(agent, user_input, context, model)
            debate_trace[agent_id] = text
            meta_trace[agent_id] = {
                "model": getattr(model, "model_name", "unknown"),
                "provider": provider,
            }

        await asyncio.gather(*(_run_one(a) for a in selected_agents))

        # Run synthesizer if not already in the selection — collapses the three perspectives.
        if "synthesizer" in self.agents and "synthesizer" not in selected_agents:
            syn_agent = self.agents["synthesizer"]
            syn_model = self._pick_model_for_agent(syn_agent, used_providers)
            syn_text = await self._invoke_synthesizer(
                syn_agent, user_input, context, debate_trace, syn_model
            )
            debate_trace["synthesizer"] = syn_text
            meta_trace["synthesizer"] = {
                "model": getattr(syn_model, "model_name", "unknown"),
                "provider": getattr(syn_model, "provider_name", "unknown"),
            }

        debate_trace["__meta__"] = meta_trace  # type: ignore[assignment]
        return debate_trace

    # ---------- internals ----------

    def _pick_model_for_agent(self, agent: EnsembleAgent, used_providers: List[str]):
        """Pick the highest-scoring allowed model the agent's provider hint matches; else next in failover chain."""
        try:
            chain = self.model_router.get_failover_chain(agent.preferred_capabilities, max_models=8)
        except Exception:
            chain = [self.model_router.get_model(agent.preferred_capabilities)]
        if not chain:
            return self.model_router.get_model(agent.preferred_capabilities)

        # Prefer hinted provider when not already used.
        if agent.provider_hint:
            for m in chain:
                if getattr(m, "provider_name", "") == agent.provider_hint and getattr(m, "provider_name", "") not in used_providers:
                    return m

        # Otherwise pick the first model whose provider hasn't been used yet.
        for m in chain:
            if getattr(m, "provider_name", "") not in used_providers:
                return m

        # Fall back to the top-scoring model.
        return chain[0]

    async def _invoke(self, agent: EnsembleAgent, user_input: str, context: Dict[str, Any], model) -> str:
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
            resp = await model.chat([{"role": "user", "content": prompt}])
            if isinstance(resp, str):
                return resp.replace(f"{agent.name}:", "").strip()
            return str(resp)
        except Exception as e:
            viki_logger.error("Ensemble Agent %s failed: %s", agent.name, e)
            return "Unable to generate perspective."

    async def _invoke_synthesizer(
        self,
        agent: EnsembleAgent,
        user_input: str,
        context: Dict[str, Any],
        perspectives: Dict[str, str],
        model,
    ) -> str:
        identity = context.get("narrative_identity", "A helpful AI assistant.")
        bullets = "\n".join(
            f"- {persona.upper()}: {text}"
            for persona, text in perspectives.items()
            if persona not in ("synthesizer", "__meta__")
        )
        prompt = (
            f"SYSTEM: You are the Synthesizer in VIKI's cross-provider ensemble.\n"
            f"ROLE: {agent.role}\n"
            f"INSTRUCTION: {agent.instruction}\n\n"
            f"IDENTITY: {identity}\n\n"
            f"USER INPUT: {user_input}\n\n"
            f"OTHER AGENTS' PERSPECTIVES:\n{bullets}\n\n"
            f"Produce one coherent integrated perspective (<=120 words). "
            f"Resolve contradictions; do not just list the agents."
        )
        try:
            resp = await model.chat([{"role": "user", "content": prompt}])
            if isinstance(resp, str):
                return resp.strip()
            return str(resp)
        except Exception as e:
            viki_logger.error("Ensemble Synthesizer failed: %s", e)
            return "Unable to synthesize perspectives."

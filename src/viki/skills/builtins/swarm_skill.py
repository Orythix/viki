import asyncio
from typing import Any

from viki.application.services.swarm_orchestrator import (
    SwarmOrchestrator,
    plan_dag,
)
from viki.config.logger import viki_logger
from viki.infrastructure.swarm.message_bus import SwarmMessage, SwarmMessageBus
from viki.skills.base import BaseSkill


class SwarmSkill(BaseSkill):
    """
    Sub-Agent Swarm (The Council).
    Delegates specialized tasks to sub-agents managed by the SwarmOrchestrator.
    Supports parallel worker execution, DAG-based task decomposition,
    and inter-agent messaging.
    """

    def __init__(self, orchestrator: SwarmOrchestrator, controller):
        self._orchestrator = orchestrator
        self.controller = controller
        self._message_bus: SwarmMessageBus | None = None

    def _get_bus(self) -> SwarmMessageBus:
        if self._message_bus is None:
            self._message_bus = SwarmMessageBus()
            self._orchestrator.set_message_bus(self._message_bus)
        return self._message_bus

    @property
    def name(self) -> str:
        return "swarm_control"

    @property
    def description(self) -> str:
        return (
            "Delegates specialized tasks to a council of sub-agents "
            "(Researcher, Architect, Critic, or custom DAG). "
            "Use for parallel research, complex design, multi-perspective reviews, "
            "or dependency-ordered task plans."
        )

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "delegate_council",
                        "dag_delegate",
                        "status",
                        "terminate",
                        "bus_stats",
                    ],
                    "description": (
                        "delegate_council: parallel research+coder+reviewer. "
                        "dag_delegate: auto-decompose objective into dependency DAG. "
                        "status: swarm state overview. "
                        "terminate: release an agent. "
                        "bus_stats: inter-agent message bus stats."
                    ),
                },
                "objective": {
                    "type": "string",
                    "description": (
                        "The complex objective (required for 'delegate_council' and 'dag_delegate')."
                    ),
                },
                "agent_id": {
                    "type": "string",
                    "description": "Specific agent ID (for 'terminate').",
                },
            },
            "required": ["action"],
        }

    @property
    def safety_tier(self) -> str:
        return "medium"

    async def execute(self, params: dict[str, Any]) -> str:
        action = params.get("action")

        if action == "delegate_council":
            return await self._delegate_council(params)
        elif action == "dag_delegate":
            return await self._dag_delegate(params)
        elif action == "status":
            status = self._orchestrator.get_swarm_status()
            return f"Swarm Status: {status}"
        elif action == "terminate":
            agent_id = params.get("agent_id")
            if not agent_id:
                return "Error: Agent ID is required for termination."
            self._orchestrator.agent_pool.release_agent(agent_id)
            return f"Agent {agent_id} has been released."
        elif action == "bus_stats":
            bus = self._get_bus()
            return f"Message Bus: {bus.stats()}"

        return f"Unknown swarm action: {action}"

    async def _delegate_council(self, params: dict[str, Any]) -> str:
        objective = params.get("objective", "")
        if not objective:
            return "Error: No objective provided."

        viki_logger.info("Swarm: Convoking the council for '%s'", objective)

        specialties = ["research", "coder", "reviewer"]
        workers = []

        for specialty in specialties:
            task = await self._orchestrator.delegate_task(
                f"{specialty} analysis for: {objective}", specialty
            )
            workers.append(self._execute_worker(task, specialty, objective, self._get_bus()))

        results = await asyncio.gather(*workers)

        synthesis = [
            {
                "role": "system",
                "content": (
                    "You are VIKI Manager. Compile the following worker reports "
                    "into a final comprehensive master report."
                ),
            },
            {
                "role": "user",
                "content": f"Objective: {objective}\n\nREPORTS:\n" + "\n---\n".join(results),
            },
        ]

        model = self.controller.model_router.get_model(capabilities=["reasoning"])
        final_report = await model.chat(synthesis)

        return f"CONSOLIDATED COUNCIL REPORT:\n\n{final_report}"

    async def _dag_delegate(self, params: dict[str, Any]) -> str:
        objective = params.get("objective", "")
        if not objective:
            return "Error: No objective provided."

        viki_logger.info("Swarm: DAG-delegating '%s'", objective)
        nodes = plan_dag(objective)

        completed = await self._orchestrator.execute_dag(
            objective,
            self._execute_worker,
            nodes=nodes,
        )

        summary = self._orchestrator.get_dag_summary(completed)

        # Synthesize final report from all completed nodes
        completed_nodes = [n for n in completed if n.status == "completed" and n.result]
        if completed_nodes:
            reports = "\n---\n".join(
                f"[{n.specialty}] {n.description}\n{n.result}" for n in completed_nodes
            )
            synthesis = [
                {
                    "role": "system",
                    "content": (
                        "You are VIKI Manager. Synthesize the following DAG task results "
                        "into a coherent final report."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Objective: {objective}\n\nTASK RESULTS:\n{reports}",
                },
            ]
            model = self.controller.model_router.get_model(capabilities=["reasoning"])
            final_report = await model.chat(synthesis)
            return f"{summary}\n\nFINAL SYNTHESIS:\n\n{final_report}"

        return summary

    async def _execute_worker(
        self,
        task: Any,
        specialty: str,
        objective: str,
        message_bus: SwarmMessageBus | None = None,
    ) -> str:
        """Execute a specialized worker agent via the LLM."""
        sys_prompts = {
            "research": (
                "You are the Researcher Agent. Investigate facts, context, and prior art "
                "for this objective. Be thorough and cite specifics."
            ),
            "coder": (
                "You are the Architect Agent. Define structure, logic, and implementation "
                "approach. Be precise about components and their interactions."
            ),
            "reviewer": (
                "You are the Critic Agent. Review for flaws, edge cases, security concerns, "
                "and missing requirements. Be constructive."
            ),
            "general": ("You are a generalist agent. Analyze and report on the given objective."),
        }

        messages = [
            {
                "role": "system",
                "content": sys_prompts.get(specialty, "You are a specialized worker."),
            },
            {"role": "user", "content": objective},
        ]

        # Include any inter-agent messages if available
        if message_bus is not None:
            recent = message_bus.get_history(channel=specialty, limit=5)
            if recent:
                context = "\n".join(f"[from {m.sender_name}]: {m.content[:200]}" for m in recent)
                messages.insert(
                    1,
                    {
                        "role": "system",
                        "content": f"Messages from other agents:\n{context}",
                    },
                )

        model = self.controller.model_router.get_model(capabilities=["fast_response"])
        report = await model.chat(messages)

        task.status = "completed"
        task.result = report
        self._orchestrator.agent_pool.release_agent(task.assigned_to)

        # Publish result to message bus so other agents can reference it
        if message_bus is not None:
            agent = self._orchestrator.agent_pool.get_agent_by_id(task.assigned_to)
            agent_name = agent.name if agent else specialty
            await message_bus.publish(
                SwarmMessage(
                    sender_id=task.assigned_to or "",
                    sender_name=agent_name,
                    channel=specialty,
                    content=f"Completed {specialty} analysis. Key findings: {report[:300]}",
                )
            )

        return f"[{specialty.upper()} REPORT]\n{report}"

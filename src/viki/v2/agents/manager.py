"""AgentManager — spawns, monitors, and coordinates specialist agents."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from .architect_agent import ArchitectAgent
from .base import AgentFindings, AgentResult, SpecialistAgent
from .data_agent import DataAgent
from .developer_agent import DeveloperAgent
from .devops_agent import DevOpsAgent
from .qa_agent import QAAgent
from .research_agent import ResearchAgent
from .security_agent import SecurityAgent

logger = logging.getLogger(__name__)

AGENT_REGISTRY: dict[str, type[SpecialistAgent]] = {
    "architect": ArchitectAgent,
    "developer": DeveloperAgent,
    "security": SecurityAgent,
    "research": ResearchAgent,
    "devops": DevOpsAgent,
    "data": DataAgent,
    "qa": QAAgent,
}


@dataclass
class DispatchReport:
    goal: str
    results: dict[str, AgentFindings] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)


class AgentManager:
    """Manages the lifecycle and dispatch of specialist agents."""

    def __init__(self, llm_client=None, tool_registry=None):
        self._agents: dict[str, SpecialistAgent] = {}
        self._llm = llm_client
        self._tool_registry = tool_registry
        self._init_agents()

    def _init_agents(self):
        for name, cls in AGENT_REGISTRY.items():
            try:
                self._agents[name] = cls(llm_client=self._llm, tool_registry=self._tool_registry)
            except Exception as e:
                logger.warning("Agent %s failed to initialize: %s", name, e)

    def get_agent(self, name: str) -> SpecialistAgent | None:
        return self._agents.get(name)

    def list_agents(self) -> list[str]:
        return list(self._agents.keys())

    def register_agent(self, name: str, agent: SpecialistAgent):
        self._agents[name] = agent

    async def analyze(self, agent_name: str, context: dict) -> AgentFindings:
        agent = self._agents.get(agent_name)
        if agent is None:
            return AgentFindings(
                summary=f"Agent '{agent_name}' not available",
                confidence=0.0,
                risks=["Agent unavailable"],
                recommendations=[],
            )
        try:
            return await agent.analyze(context)
        except Exception as e:
            logger.error("Agent %s.analyze failed: %s", agent_name, e)
            return AgentFindings(
                summary=f"Analysis failed: {e}",
                confidence=0.0,
                risks=[str(e)],
                recommendations=[],
            )

    async def execute(self, agent_name: str, context: dict) -> AgentResult:
        agent = self._agents.get(agent_name)
        if agent is None:
            return AgentResult(success=False, output=f"Agent '{agent_name}' not available")
        try:
            return await agent.execute(context)
        except Exception as e:
            logger.error("Agent %s.execute failed: %s", agent_name, e)
            return AgentResult(success=False, output=str(e))

    async def dispatch_all(
        self,
        goal: str,
        context: dict | None = None,
        on_agent: Callable[[str, str], None] | None = None,
    ) -> DispatchReport:
        """Run all agents' analyze in parallel for a given goal.

        Parameters
        ----------
        on_agent :
            Called with ``(agent_name, status)`` where status is
            ``"start"`` or ``"complete"``.
        """
        ctx = {"goal": goal, **(context or {})}
        report = DispatchReport(goal=goal)

        async def _run(name: str) -> tuple[str, AgentFindings | None, str | None]:
            try:
                if on_agent:
                    on_agent(name, "start")
                findings = await self.analyze(name, ctx)
                if on_agent:
                    on_agent(name, "complete")
                return name, findings, None
            except Exception as e:
                return name, None, str(e)

        tasks = [_run(name) for name in self._agents]
        for coro in asyncio.as_completed(tasks):
            name, findings, error = await coro
            if error:
                report.errors[name] = error
            elif findings:
                report.results[name] = findings

        return report

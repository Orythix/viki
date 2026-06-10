from typing import Dict, List, Optional
from domain.entities.swarm import SubAgent, AgentStatus
from domain.interfaces.agent_pool import IAgentPool

class LocalAgentPool(IAgentPool):
    def __init__(self):
        self._agents: Dict[str, SubAgent] = {}

    def provision_agent(self, specialty: str) -> SubAgent:
        agent = SubAgent(name=f"SubAgent-{len(self._agents)+1}", specialty=specialty)
        self._agents[agent.id] = agent
        return agent

    def release_agent(self, agent_id: str) -> None:
        if agent_id in self._agents:
            self._agents[agent_id].status = AgentStatus.IDLE
            self._agents[agent_id].current_task = None

    def get_active_agents(self) -> List[SubAgent]:
        return list(self._agents.values())

    def get_agent_by_id(self, agent_id: str) -> Optional[SubAgent]:
        return self._agents.get(agent_id)

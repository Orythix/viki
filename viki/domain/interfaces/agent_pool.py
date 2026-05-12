from abc import ABC, abstractmethod
from typing import List, Optional
from viki.domain.entities.swarm import SubAgent, SwarmTask

class IAgentPool(ABC):
    @abstractmethod
    def provision_agent(self, specialty: str) -> SubAgent:
        """Create or acquire an agent for a specific specialty."""
        pass

    @abstractmethod
    def release_agent(self, agent_id: str) -> None:
        """Release an agent back to the pool or terminate it."""
        pass

    @abstractmethod
    def get_active_agents(self) -> List[SubAgent]:
        """Return a list of currently active sub-agents."""
        pass

    @abstractmethod
    def get_agent_by_id(self, agent_id: str) -> Optional[SubAgent]:
        """Find a specific agent."""
        pass

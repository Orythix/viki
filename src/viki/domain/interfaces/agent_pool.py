from abc import ABC, abstractmethod

from viki.domain.entities.swarm import SubAgent


class IAgentPool(ABC):
    @abstractmethod
    def provision_agent(self, specialty: str) -> SubAgent:
        """Create or acquire an agent for a specific specialty."""

    @abstractmethod
    def release_agent(self, agent_id: str) -> None:
        """Release an agent back to the pool or terminate it."""

    @abstractmethod
    def get_active_agents(self) -> list[SubAgent]:
        """Return a list of currently active sub-agents."""

    @abstractmethod
    def get_agent_by_id(self, agent_id: str) -> SubAgent | None:
        """Find a specific agent."""

from typing import List, Optional
from domain.entities.swarm import SubAgent, SwarmTask, AgentStatus
from domain.interfaces.agent_pool import IAgentPool
from config.logger import viki_logger

class SwarmOrchestrator:
    def __init__(self, agent_pool: IAgentPool):
        self.agent_pool = agent_pool
        self.tasks: List[SwarmTask] = []

    async def delegate_task(self, description: str, specialty: str = "general") -> SwarmTask:
        """Provision an agent and assign a task."""
        viki_logger.info(f"Delegating task: {description} (Specialty: {specialty})")
        
        agent = self.agent_pool.provision_agent(specialty)
        task = SwarmTask(description=description, assigned_to=agent.id)
        
        agent.status = AgentStatus.BUSY
        agent.current_task = task.id
        
        self.tasks.append(task)
        return task

    def get_swarm_status(self) -> dict:
        """Returns a summary of the current swarm state."""
        agents = self.agent_pool.get_active_agents()
        return {
            "total_agents": len(agents),
            "busy_agents": len([a for a in agents if a.status == AgentStatus.BUSY]),
            "pending_tasks": len([t for t in self.tasks if t.status == "pending"])
        }

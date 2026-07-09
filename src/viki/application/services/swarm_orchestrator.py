import asyncio
import uuid
from typing import Any

from viki.config.logger import viki_logger
from viki.domain.entities.swarm import AgentStatus, SwarmTask
from viki.domain.interfaces.agent_pool import IAgentPool


class DAGNode:
    """A single node in a task dependency graph."""

    def __init__(
        self,
        task_id: str,
        description: str,
        specialty: str = "general",
        depends_on: list[str] | None = None,
    ):
        self.task_id = task_id
        self.description = description
        self.specialty = specialty
        self.depends_on = depends_on or []
        self.result: str | None = None
        self.status: str = "pending"  # pending | running | completed | failed


def plan_dag(objective: str) -> list[DAGNode]:
    """Decompose a complex objective into a DAG of sub-tasks.

    Returns an ordered list of DAGNode in topological order (dependencies first).
    """
    nodes = [
        DAGNode(
            task_id=str(uuid.uuid4()),
            description=f"Research background and context for: {objective}",
            specialty="research",
        ),
        DAGNode(
            task_id=str(uuid.uuid4()),
            description=f"Design architecture and structure for: {objective}",
            specialty="coder",
            depends_on=[],  # can run in parallel with research
        ),
        DAGNode(
            task_id=str(uuid.uuid4()),
            description=f"Analyze risks and edge cases for: {objective}",
            specialty="reviewer",
            depends_on=[],  # can run in parallel
        ),
        DAGNode(
            task_id=str(uuid.uuid4()),
            description=f"Synthesize research, architecture, and review into final plan for: {objective}",
            specialty="general",
            depends_on=[],  # depends on all three above — set at runtime
        ),
    ]
    # Wire the synthesis node to depend on the first three
    for i in range(3):
        nodes[3].depends_on.append(nodes[i].task_id)

    return nodes


class SwarmOrchestrator:
    def __init__(self, agent_pool: IAgentPool):
        self.agent_pool = agent_pool
        self.tasks: list[SwarmTask] = []
        self._message_bus = None

    def set_message_bus(self, bus: Any) -> None:
        self._message_bus = bus

    async def delegate_task(self, description: str, specialty: str = "general") -> SwarmTask:
        """Provision an agent and assign a task."""
        viki_logger.info("Delegating task: %s (Specialty: %s)", description, specialty)

        agent = self.agent_pool.provision_agent(specialty)
        task = SwarmTask(description=description, assigned_to=agent.id)

        agent.status = AgentStatus.BUSY
        agent.current_task = task.id

        self.tasks.append(task)
        return task

    async def execute_dag(
        self,
        objective: str,
        worker_fn: Any,
        nodes: list[DAGNode] | None = None,
    ) -> list[DAGNode]:
        """Execute a DAG of tasks in dependency order, fanning out parallel work."""
        if nodes is None:
            nodes = plan_dag(objective)
        if not nodes:
            return []

        completed: set[str] = set()
        results: list[DAGNode] = []

        while len(completed) < len(nodes):
            # Find nodes whose dependencies are all met
            ready = [
                n
                for n in nodes
                if n.task_id not in completed
                and n.status == "pending"
                and all(dep in completed for dep in n.depends_on)
            ]
            if not ready:
                viki_logger.warning("DAG stalled — possible circular dependency")
                break

            # Execute ready nodes in parallel
            batch_results = await asyncio.gather(
                *[self._run_node(n, worker_fn, objective) for n in ready],
                return_exceptions=True,
            )

            for node, result in zip(ready, batch_results, strict=False):
                if isinstance(result, Exception):
                    node.status = "failed"
                    viki_logger.error("DAG node %s failed: %s", node.task_id, result)
                else:
                    node.status = "completed"
                    node.result = str(result)
                completed.add(node.task_id)
                results.append(node)

        return results

    async def _run_node(self, node: DAGNode, worker_fn: Any, objective: str) -> str:
        node.status = "running"
        task: SwarmTask | None = None
        try:
            task = await self.delegate_task(node.description, node.specialty)
            result = await worker_fn(task, node.specialty, objective, self._message_bus)
            node.result = str(result)
            node.status = "completed"
            return str(result)
        except Exception:
            node.status = "failed"
            raise
        finally:
            if task and task.assigned_to:
                self.agent_pool.release_agent(task.assigned_to)

    def get_swarm_status(self) -> dict[str, Any]:
        """Returns a summary of the current swarm state."""
        agents = self.agent_pool.get_active_agents()
        return {
            "total_agents": len(agents),
            "busy_agents": len([a for a in agents if a.status == AgentStatus.BUSY]),
            "idle_agents": len([a for a in agents if a.status == AgentStatus.IDLE]),
            "failed_agents": len([a for a in agents if a.status == AgentStatus.FAILED]),
            "total_tasks": len(self.tasks),
            "pending_tasks": len([t for t in self.tasks if t.status == "pending"]),
            "completed_tasks": len([t for t in self.tasks if t.status == "completed"]),
            "failed_tasks": len([t for t in self.tasks if t.status == "failed"]),
        }

    def get_dag_summary(self, nodes: list[DAGNode]) -> str:
        """Human-readable DAG execution summary."""
        lines = ["DAG Execution Summary:", ""]
        for node in nodes:
            dep_count = len(node.depends_on)
            deps = f" (waits on {dep_count} tasks)" if dep_count else ""
            status_icon = {"completed": "✓", "failed": "✗", "running": "→", "pending": "○"}.get(
                node.status, "?"
            )
            lines.append(f"  {status_icon} [{node.specialty}] {node.description[:70]}{deps}")
            if node.result:
                lines.append(f"      → {node.result[:100]}...")
        lines.append("")
        completed = sum(1 for n in nodes if n.status == "completed")
        failed = sum(1 for n in nodes if n.status == "failed")
        lines.append(f"Result: {completed} completed, {failed} failed, {len(nodes)} total")
        return "\n".join(lines)

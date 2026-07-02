"""ContextManager — cross-session project context via ProjectMemory."""

from __future__ import annotations

from ..memory import ProjectMemory


class ContextManager:
    """Manages cross-session project context.

    Wraps ProjectMemory with convenience methods for agent workflows.
    """

    def __init__(self, project_memory: ProjectMemory | None = None):
        self._memory = project_memory or ProjectMemory()

    async def get_context(self, project_name: str) -> dict:
        """Retrieve all context for the active project."""
        info = await self._memory.get_active_project()
        decisions = await self._memory.get_recent_decisions()
        return {
            "project": info,
            "decisions": decisions,
        }

    async def record_decision(self, project_name: str, decision: str, rationale: str):
        """Record an architectural or design decision."""
        await self._memory.record_decision(
            topic=project_name,
            decision=decision,
            reasoning=rationale,
        )

    async def summarize_session(self, project_name: str, summary: str):
        """Store a session summary for future reference."""
        await self._memory.set_context(
            key=f"session_summary:{project_name}",
            value=summary,
        )

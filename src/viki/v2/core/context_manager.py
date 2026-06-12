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
        """Retrieve all context for a project."""
        info = self._memory.get_project(project_name)
        decisions = self._memory.get_decisions(project_name)
        return {
            "project": info,
            "decisions": decisions,
        }

    async def record_decision(self, project_name: str, decision: str, rationale: str):
        """Record an architectural or design decision."""
        self._memory.add_decision(
            project_name=project_name,
            decision=decision,
            rationale=rationale,
        )

    async def summarize_session(self, project_name: str, summary: str):
        """Store a session summary for future reference."""
        self._memory.add_context(
            project_name=project_name,
            key="session_summary",
            value=summary,
        )

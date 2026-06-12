"""QAAgent — tests, coverage, linting, validation."""

from __future__ import annotations

from ..llm import get_llm_client
from .base import ActionPlan, AgentFindings, AgentResult, SpecialistAgent


class QAAgent(SpecialistAgent):
    name = "qa"
    description = "Analyzes test coverage, runs linting, and validates code quality"
    domain = "qa"

    def __init__(self, llm_client=None, tool_registry=None):
        super().__init__(llm_client or get_llm_client(), tool_registry)

    async def analyze(self, context: dict) -> AgentFindings:
        goal = context.get("goal", "Unknown")
        test_info = context.get("test_info", "")
        lint_results = context.get("lint_results", "")
        prompt = (
            f"You are an expert QA engineer. "
            f"Analyze the quality context and produce findings.\n\n"
            f"Goal: {goal}\n"
            f"Test info: {test_info}\n"
            f"Lint results: {lint_results}\n\n"
            f"Return JSON with: summary, confidence (0-1), risks (list), recommendations (list)."
        )
        data = await self._llm.structured_output(
            prompt,
            {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "confidence": {"type": "number"},
                    "risks": {"type": "array", "items": {"type": "string"}},
                    "recommendations": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["summary", "confidence", "risks", "recommendations"],
            },
        )
        return AgentFindings(**data)

    async def execute(self, plan: ActionPlan) -> AgentResult:
        results = []
        for step in plan.steps:
            tool = step.get("tool", "")
            params = step.get("params", {})
            result = (
                await self._tool_registry.execute(tool, params) if self._tool_registry else None
            )
            results.append(f"{tool}: {'OK' if result and result.success else 'FAIL'}")
        return AgentResult(
            success=True,
            output="\n".join(results),
            artifacts=[],
        )

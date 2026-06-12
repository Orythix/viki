"""SecurityAgent — vulnerability scanning, secrets detection, dependency audit."""

from __future__ import annotations

from ..llm import get_llm_client
from .base import ActionPlan, AgentFindings, AgentResult, SpecialistAgent


class SecurityAgent(SpecialistAgent):
    name = "security"
    description = "Scans for vulnerabilities, secrets, and dependency issues"
    domain = "security"

    def __init__(self, llm_client=None, tool_registry=None):
        super().__init__(llm_client or get_llm_client(), tool_registry)

    async def analyze(self, context: dict) -> AgentFindings:
        goal = context.get("goal", "Unknown")
        repo_info = context.get("repo_info", "")
        scan_results = context.get("scan_results", "")
        prompt = (
            f"You are an expert security engineer. "
            f"Analyze the security context and produce findings.\n\n"
            f"Goal: {goal}\n"
            f"Repository: {repo_info}\n"
            f"Scan results: {scan_results}\n\n"
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

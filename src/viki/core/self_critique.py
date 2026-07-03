"""SelfCritique — quality assurance loop for agent outputs with LLM response cache."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from viki._compat import StrEnum

logger = logging.getLogger(__name__)

_CACHE_TTL = 60


class CritiqueLevel(StrEnum):
    NONE = "none"
    LIGHT = "light"
    FULL = "full"


@dataclass
class CritiqueIssue:
    category: str = ""
    description: str = ""
    severity: str = "medium"


@dataclass
class CritiqueResult:
    score: float = 1.0
    issues: list[CritiqueIssue] = field(default_factory=list)
    passed: bool = True


class _CritiqueResponse(BaseModel):
    score: float
    issues: list[dict[str, str]]
    passed: bool


_CRITIQUE_LEVEL_MAP: dict[str, CritiqueLevel] = {
    "time": CritiqueLevel.NONE,
    "date": CritiqueLevel.NONE,
    "weather": CritiqueLevel.NONE,
    "ip": CritiqueLevel.NONE,
    "shell": CritiqueLevel.NONE,
    "execute": CritiqueLevel.NONE,
    "factual": CritiqueLevel.NONE,
    "function": CritiqueLevel.LIGHT,
    "script": CritiqueLevel.LIGHT,
    "refactor": CritiqueLevel.FULL,
    "design": CritiqueLevel.FULL,
    "schema": CritiqueLevel.FULL,
    "database": CritiqueLevel.FULL,
    "module": CritiqueLevel.FULL,
    "class": CritiqueLevel.FULL,
    "architecture": CritiqueLevel.FULL,
    "pipeline": CritiqueLevel.FULL,
}


class SelfCritique:
    """Reviews agent outputs and suggests improvements before delivery.

    Supports three levels:
      - NONE: skip critique (factual/deterministic responses)
      - LIGHT: check correctness + style
      - FULL: check correctness + completeness + safety + style + efficiency
    """

    def __init__(self, llm_client: Any = None):
        self._llm = llm_client
        self._cache: dict[int, tuple[float, CritiqueResult | str]] = {}

    @staticmethod
    def detect_level(task: str) -> CritiqueLevel:
        """Determine critique level based on task content."""
        import re

        lower = task.lower()
        for keyword, level in _CRITIQUE_LEVEL_MAP.items():
            if re.search(r"\b" + re.escape(keyword) + r"\b", lower):
                return level
        return CritiqueLevel.LIGHT

    async def critique(self, task: str, solution: str) -> CritiqueResult:
        """Review a solution and identify weaknesses. Results cached for _CACHE_TTL."""
        if not self._llm:
            return CritiqueResult(passed=True, score=1.0)

        level = self.detect_level(task)
        if level == CritiqueLevel.NONE:
            return CritiqueResult(passed=True, score=1.0)

        key = hash((task, solution))
        cached = self._cache.get(key)
        if cached is not None:
            ts, result = cached
            if time.monotonic() - ts < _CACHE_TTL and isinstance(result, CritiqueResult):
                return result

        checks = self._build_checks(level)
        prompt = (
            f"You are a code reviewer. Review this solution.\n\n"
            f"Task: {task}\n\n"
            f"Solution:\n{solution}\n\n"
            f"Check the following:\n{checks}\n\n"
            f"Return JSON with: score (0.0-1.0), issues (array of {{category, description, severity}}), "
            f"passed (true if no critical issues)."
        )
        try:
            messages = [
                {
                    "role": "system",
                    "content": "You are a precise code reviewer. Return only valid JSON.",
                },
                {"role": "user", "content": prompt},
            ]
            data = await self._llm.chat_structured(messages, _CritiqueResponse)
            issues = [CritiqueIssue(**i) for i in data.issues]
            result = CritiqueResult(
                score=data.score,
                issues=issues,
                passed=data.passed,
            )
            self._cache[key] = (time.monotonic(), result)
            return result
        except Exception as e:
            logger.warning("SelfCritique failed: %s", e)
            return CritiqueResult(passed=True, score=1.0)

    async def improve(self, task: str, solution: str, critique: CritiqueResult) -> str:
        """Rewrite the solution addressing all critique issues. Result cached."""
        if not self._llm:
            return solution
        if critique.passed or not critique.issues:
            return solution

        key = hash((task, solution, tuple(i.description for i in critique.issues)))
        cached = self._cache.get(key)
        if cached is not None:
            ts, result = cached
            if time.monotonic() - ts < _CACHE_TTL and isinstance(result, str):
                return result

        issues_text = "\n".join(
            f"- [{i.severity}] {i.category}: {i.description}" for i in critique.issues
        )
        messages = [
            {
                "role": "system",
                "content": "You are a code reviewer. Rewrite solutions to fix all identified issues.",
            },
            {
                "role": "user",
                "content": f"Original task: {task}\n\nCurrent solution:\n{solution}\n\nIssues to fix:\n{issues_text}\n\nRewrite the solution fixing ALL issues above. Return only the improved solution.",
            },
        ]
        try:
            improved = await self._llm.chat(messages)
            self._cache[key] = (time.monotonic(), improved)
            return improved
        except Exception as e:
            logger.warning("SelfCritique.improve failed: %s", e)
            return solution

    async def refine(
        self,
        task: str,
        solution: str,
        max_iterations: int = 3,
        score_threshold: float = 0.85,
        min_improvement: float = 0.05,
    ) -> tuple[str, list[CritiqueResult]]:
        """Iteratively critique and improve a solution until convergence.

        Each iteration: critique → improve → re-critique.
        Stops when:
        - score >= score_threshold, or
        - score improvement < min_improvement (converged), or
        - max_iterations reached.

        Returns (final_solution, list_of_critique_results_per_iteration).
        """
        current = solution
        results: list[CritiqueResult] = []

        for i in range(max_iterations):
            cr = await self.critique(task, current)
            results.append(cr)

            if cr.passed or cr.score >= score_threshold:
                logger.info("Refine: converged at iteration %d (score=%.2f)", i + 1, cr.score)
                break

            if i > 0:
                prev_score = results[-2].score
                delta = cr.score - prev_score
                if delta < min_improvement:
                    logger.info(
                        "Refine: plateau at iteration %d (score=%.2f, delta=%.2f)",
                        i + 1,
                        cr.score,
                        delta,
                    )
                    break

            improved = await self.improve(task, current, cr)
            if improved == current:
                logger.info("Refine: no change at iteration %d, stopping", i + 1)
                break
            current = improved

        return current, results

    @staticmethod
    def _build_checks(level: CritiqueLevel) -> str:
        base = "1. Correctness — does it solve the task?\n"
        if level == CritiqueLevel.LIGHT:
            return base + "2. Style — follows best practices?\n"
        return (
            base
            + "2. Completeness — are there edge cases?\n"
            + "3. Safety — any security or data loss risks?\n"
            + "4. Style — follows best practices?\n"
            + "5. Efficiency — could it be simpler?\n"
        )

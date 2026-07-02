"""SelfCritique — quality assurance loop for agent outputs with LLM response cache."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from viki._compat import StrEnum

from ..llm import get_llm_client

logger = logging.getLogger(__name__)

_CACHE_TTL = 60  # seconds


class CritiqueLevel(StrEnum):
    NONE = "none"
    LIGHT = "light"
    FULL = "full"


@dataclass
class CritiqueIssue:
    category: str = ""
    description: str = ""
    severity: str = "medium"  # low | medium | high


@dataclass
class CritiqueResult:
    score: float = 1.0
    issues: list[CritiqueIssue] = field(default_factory=list)
    passed: bool = True


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

    def __init__(self, llm_client=None):
        self._llm = llm_client or get_llm_client()
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
        level = self.detect_level(task)
        if level == CritiqueLevel.NONE:
            return CritiqueResult(passed=True, score=1.0)

        # Check cache before LLM call
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
        schema = {
            "type": "object",
            "properties": {
                "score": {"type": "number"},
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "category": {"type": "string"},
                            "description": {"type": "string"},
                            "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                        },
                        "required": ["category", "description", "severity"],
                    },
                },
                "passed": {"type": "boolean"},
            },
            "required": ["score", "issues", "passed"],
        }
        try:
            data = await self._llm.structured_output(prompt, schema)
            issues = [CritiqueIssue(**i) for i in data.get("issues", [])]
            result = CritiqueResult(
                score=data.get("score", 1.0),
                issues=issues,
                passed=data.get("passed", len(issues) == 0),
            )
            self._cache[key] = (time.monotonic(), result)
            return result
        except Exception as e:
            logger.warning("SelfCritique failed: %s", e)
            return CritiqueResult(passed=True, score=1.0)

    async def improve(self, task: str, solution: str, critique: CritiqueResult) -> str:
        """Rewrite the solution addressing all critique issues. Result cached."""
        if critique.passed or not critique.issues:
            return solution

        # Check cache
        key = hash((task, solution, tuple(i.description for i in critique.issues)))
        cached = self._cache.get(key)
        if cached is not None:
            ts, result = cached
            if time.monotonic() - ts < _CACHE_TTL and isinstance(result, str):
                return result

        issues_text = "\n".join(
            f"- [{i.severity}] {i.category}: {i.description}" for i in critique.issues
        )
        prompt = (
            f"Original task: {task}\n\n"
            f"Current solution:\n{solution}\n\n"
            f"Issues to fix:\n{issues_text}\n\n"
            f"Rewrite the solution fixing ALL issues above. Return only the improved solution."
        )
        try:
            improved = await self._llm.chat([{"role": "user", "content": prompt}])
            self._cache[key] = (time.monotonic(), improved)
            return improved
        except Exception as e:
            logger.warning("SelfCritique.improve failed: %s", e)
            return solution

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

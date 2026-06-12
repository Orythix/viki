"""SpecialistAgent — abstract base for domain-specialist sub-agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentFindings:
    summary: str = ""
    confidence: float = 0.0
    risks: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class AgentResult:
    success: bool = False
    output: str = ""
    artifacts: list[str] = field(default_factory=list)


@dataclass
class ActionPlan:
    steps: list[dict[str, Any]] = field(default_factory=list)
    estimated_complexity: str = "low"


class SpecialistAgent(ABC):
    name: str = ""
    description: str = ""
    domain: str = ""

    def __init__(self, llm_client=None, tool_registry=None):
        self._llm = llm_client
        self._tool_registry = tool_registry

    @abstractmethod
    async def analyze(self, context: dict[str, Any]) -> AgentFindings:
        ...

    @abstractmethod
    async def execute(self, plan: ActionPlan) -> AgentResult:
        ...

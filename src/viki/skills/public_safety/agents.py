"""Multi-agent coordination for Public Safety Skills Framework."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

UTC = timezone.utc
from enum import Enum
from typing import Any

from viki.skills.public_safety.base import (
    BasePublicSafetySkill,
    ConfidenceRating,
    ConfidenceScore,
    SafetyRules,
    SkillResult,
)


class AgentRole(Enum):
    INVESTIGATOR = "investigation"
    CYBERSECURITY = "cybersecurity"
    GOVERNMENT = "government"
    EMERGENCY = "emergency"
    RESEARCH = "research"
    VIKI_SAFETY = "viki_safety"


@dataclass
class AgentTask:
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    role: AgentRole = AgentRole.RESEARCH
    query: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    created_at: float = field(default_factory=time.time)
    assigned_agent: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "role": self.role.value,
            "query": self.query,
            "context": self.context,
            "priority": self.priority,
            "assigned_agent": self.assigned_agent,
        }


@dataclass
class AgentResponse:
    task_id: str = ""
    skill_name: str = ""
    success: bool = False
    data: Any = None
    error: str | None = None
    confidence: ConfidenceScore | None = None
    execution_time_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "skill_name": self.skill_name,
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "confidence": self.confidence.to_dict() if self.confidence else None,
            "execution_time_ms": self.execution_time_ms,
        }


class BaseAgent:
    """Base class for specialized agents."""

    def __init__(self, name: str, role: AgentRole):
        self._name = name
        self._role = role
        self._skills: dict[str, BasePublicSafetySkill] = {}
        self.safety = SafetyRules()
        self._task_history: list[AgentTask] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def role(self) -> AgentRole:
        return self._role

    def register_skill(self, skill: BasePublicSafetySkill):
        self._skills[skill.name] = skill

    def get_skill(self, name: str) -> BasePublicSafetySkill | None:
        return self._skills.get(name)

    def list_skills(self) -> list[str]:
        return list(self._skills.keys())

    async def process(self, task: AgentTask) -> AgentResponse:
        start = time.time()
        self._task_history.append(task)
        safety = self.safety.check(task.query, task.context)
        if not safety.passed:
            elapsed = (time.time() - start) * 1000
            return AgentResponse(
                task_id=task.task_id,
                skill_name=self._name,
                success=False,
                error=safety.reason,
                execution_time_ms=elapsed,
            )
        try:
            result = await self._process_impl(task)
            elapsed = (time.time() - start) * 1000
            return AgentResponse(
                task_id=task.task_id,
                skill_name=self._name,
                success=result.success,
                data=result.data,
                error=result.error,
                confidence=result.confidence,
                execution_time_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            return AgentResponse(
                task_id=task.task_id,
                skill_name=self._name,
                success=False,
                error=str(e),
                execution_time_ms=elapsed,
            )

    async def _process_impl(self, task: AgentTask) -> SkillResult:
        raise NotImplementedError

    def get_task_history(self, limit: int = 20) -> list[AgentTask]:
        return self._task_history[-limit:]


class InvestigationAgent(BaseAgent):
    """Handles investigative analysis across multiple domains."""

    def __init__(self):
        super().__init__(name="investigation_agent", role=AgentRole.INVESTIGATOR)

    async def _process_impl(self, task: AgentTask) -> SkillResult:
        skill = self._skills.get("investigation")
        if skill:
            return await skill.execute(task.context)
        return SkillResult(
            skill_name=self._name,
            success=False,
            error="Investigation skill not registered",
        )


class CybersecurityAgent(BaseAgent):
    """Handles cybercrime analysis, digital forensics, and threat intelligence."""

    def __init__(self):
        super().__init__(name="cybersecurity_agent", role=AgentRole.CYBERSECURITY)

    async def _process_impl(self, task: AgentTask) -> SkillResult:
        skill = self._skills.get("cybercrime")
        if skill:
            return await skill.execute(task.context)
        return SkillResult(
            skill_name=self._name,
            success=False,
            error="Cybercrime analysis skill not registered",
        )


class GovernmentAgent(BaseAgent):
    """Handles government services, policy research, and citizen assistance."""

    def __init__(self):
        super().__init__(name="government_agent", role=AgentRole.GOVERNMENT)

    async def _process_impl(self, task: AgentTask) -> SkillResult:
        skill = self._skills.get("government_services") or self._skills.get("policy_research")
        if skill:
            return await skill.execute(task.context)
        return SkillResult(
            skill_name=self._name,
            success=False,
            error="Government services skill not registered",
        )


class EmergencyAgent(BaseAgent):
    """Handles emergency response, disaster management, and public safety alerts."""

    def __init__(self):
        super().__init__(name="emergency_agent", role=AgentRole.EMERGENCY)

    async def _process_impl(self, task: AgentTask) -> SkillResult:
        skill = self._skills.get("emergency_response") or self._skills.get("disaster_management")
        if skill:
            return await skill.execute(task.context)
        return SkillResult(
            skill_name=self._name,
            success=False,
            error="Emergency response skill not registered",
        )


class VIKISafetyAgent(BaseAgent):
    """Handles AI threat detection, cyber defense, and infrastructure protection."""

    def __init__(self):
        from viki.skills.public_safety.viki_safety import VIKISafetyAgent as VSSkill

        self._skill_cls = VSSkill
        super().__init__(name="viki_safety_agent", role=AgentRole.VIKI_SAFETY)

    async def _process_impl(self, task: AgentTask) -> SkillResult:
        skill = self._skills.get("viki_safety")
        if skill:
            return await skill.execute(task.context)
        return SkillResult(
            skill_name=self._name,
            success=False,
            error="VIKI Safety skill not registered",
        )


class ResearchAgent(BaseAgent):
    """Handles OSINT research, public safety education, and fraud detection analysis."""

    def __init__(self):
        super().__init__(name="research_agent", role=AgentRole.RESEARCH)

    async def _process_impl(self, task: AgentTask) -> SkillResult:
        for skill_name in ["osint", "fraud_detection", "public_safety_education"]:
            skill = self._skills.get(skill_name)
            if skill:
                return await skill.execute(task.context)
        return SkillResult(
            skill_name=self._name,
            success=False,
            error="No suitable research skill registered",
        )


@dataclass
class CoordinationResult:
    coordinator_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task: AgentTask | None = None
    responses: list[AgentResponse] = field(default_factory=list)
    merged_data: dict[str, Any] = field(default_factory=dict)
    confidence: ConfidenceScore | None = None
    completed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "coordinator_id": self.coordinator_id,
            "task": self.task.to_dict() if self.task else None,
            "responses": [r.to_dict() for r in self.responses],
            "merged_data": self.merged_data,
            "confidence": self.confidence.to_dict() if self.confidence else None,
            "completed_at": self.completed_at,
        }


class AgentCoordinator:
    """Coordinates multiple agents for complex public safety tasks."""

    def __init__(self):
        self._agents: dict[AgentRole, BaseAgent] = {}
        self._task_queue: asyncio.Queue = asyncio.Queue()
        self._history: list[CoordinationResult] = []

    def register_agent(self, agent: BaseAgent):
        self._agents[agent.role] = agent

    def get_agent(self, role: AgentRole) -> BaseAgent | None:
        return self._agents.get(role)

    def list_agents(self) -> list[str]:
        return [a.name for a in self._agents.values()]

    def route_task(self, query: str, context: dict[str, Any] | None = None) -> list[AgentRole]:
        query_lower = query.lower()
        roles: list[AgentRole] = []

        cyber_keywords = [
            "cyber",
            "hack",
            "malware",
            "digital",
            "forensic",
            "network",
            "breach",
            "phishing",
        ]
        investigation_keywords = ["investigat", "case", "suspect", "evidence", "crime", "incident"]
        emergency_keywords = [
            "emergency",
            "disaster",
            "evacuat",
            "flood",
            "fire",
            "earthquake",
            "crisis",
        ]
        government_keywords = [
            "government",
            "policy",
            "regulation",
            "law",
            "permit",
            "license",
            "benefit",
        ]
        research_keywords = [
            "research",
            "osint",
            "open source",
            "intelligence",
            "public information",
            "fraud",
        ]

        for kw in cyber_keywords:
            if kw in query_lower and AgentRole.CYBERSECURITY not in roles:
                roles.append(AgentRole.CYBERSECURITY)
        for kw in investigation_keywords:
            if kw in query_lower and AgentRole.INVESTIGATOR not in roles:
                roles.append(AgentRole.INVESTIGATOR)
        for kw in emergency_keywords:
            if kw in query_lower and AgentRole.EMERGENCY not in roles:
                roles.append(AgentRole.EMERGENCY)
        for kw in government_keywords:
            if kw in query_lower and AgentRole.GOVERNMENT not in roles:
                roles.append(AgentRole.GOVERNMENT)
        for kw in research_keywords:
            if kw in query_lower and AgentRole.RESEARCH not in roles:
                roles.append(AgentRole.RESEARCH)

        if not roles:
            roles.append(AgentRole.RESEARCH)

        return roles

    async def execute(
        self, query: str, context: dict[str, Any] | None = None
    ) -> CoordinationResult:
        roles = self.route_task(query, context)
        ctx = dict(context or {})
        ctx.setdefault("query", query)
        task = AgentTask(query=query, context=ctx)

        tasks = []
        for role in roles:
            agent = self._agents.get(role)
            if agent:
                tasks.append(agent.process(task))

        responses = await asyncio.gather(*tasks, return_exceptions=True)

        agent_responses: list[AgentResponse] = []
        for r in responses:
            if isinstance(r, AgentResponse):
                agent_responses.append(r)
            elif isinstance(r, Exception):
                agent_responses.append(
                    AgentResponse(
                        task_id=task.task_id,
                        success=False,
                        error=str(r),
                    )
                )

        merged = self._merge_responses(agent_responses)
        confidence = self._assess_overall_confidence(agent_responses)

        result = CoordinationResult(
            task=task,
            responses=agent_responses,
            merged_data=merged,
            confidence=confidence,
        )
        self._history.append(result)
        return result

    def _merge_responses(self, responses: list[AgentResponse]) -> dict[str, Any]:
        merged: dict[str, Any] = {
            "findings": [],
            "warnings": [],
            "sources": [],
        }
        for resp in responses:
            if resp.success and resp.data:
                if isinstance(resp.data, dict):
                    for key, value in resp.data.items():
                        if key == "findings" and isinstance(value, list):
                            merged["findings"].extend(value)
                        elif key == "warnings" and isinstance(value, list):
                            merged["warnings"].extend(value)
                        elif key == "sources" and isinstance(value, list):
                            merged["sources"].extend(value)
                        else:
                            merged.setdefault(key, value)
                elif isinstance(resp.data, list):
                    merged["findings"].extend(resp.data)
            elif resp.error:
                merged["warnings"].append(f"{resp.skill_name}: {resp.error}")
        return merged

    def _assess_overall_confidence(self, responses: list[AgentResponse]) -> ConfidenceScore:
        scores = [r.confidence.score for r in responses if r.confidence]
        if not scores:
            return ConfidenceScore(ConfidenceRating.LOW, 0.3, "No confidence data available")
        avg_score = sum(scores) / len(scores)
        rating = (
            ConfidenceRating.HIGH
            if avg_score >= 0.8
            else (
                ConfidenceRating.MEDIUM
                if avg_score >= 0.5
                else (ConfidenceRating.LOW if avg_score >= 0.3 else ConfidenceRating.SPECULATIVE)
            )
        )
        return ConfidenceScore(
            rating=rating,
            score=round(avg_score, 3),
            explanation=f"Average confidence across {len(responses)} agent responses",
        )

    def get_history(self, limit: int = 10) -> list[CoordinationResult]:
        return self._history[-limit:]

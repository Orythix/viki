"""PublicSafetyOrchestrator — unified entry point for the entire safety framework.

Connects auto-learning, multi-agent coordination, NL bridge, memory, audit,
and VIKIController integration into one cohesive system.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any, cast

from viki.skills.public_safety.agents import (
    AgentCoordinator,
    BaseAgent,
    CybersecurityAgent,
    EmergencyAgent,
    GovernmentAgent,
    InvestigationAgent,
    ResearchAgent,
)
from viki.skills.public_safety.agents import (
    VIKISafetyAgent as SafetyAgent,
)
from viki.skills.public_safety.audit import (
    AuditContextManager,
    AuditStore,
)
from viki.skills.public_safety.auto_learning import get_auto_learning_engine
from viki.skills.public_safety.base import BasePublicSafetySkill, SkillResult
from viki.skills.public_safety.citizen_assistance import CitizenAssistanceSkill
from viki.skills.public_safety.cybercrime import CybercrimeAnalysisSkill
from viki.skills.public_safety.disaster_management import DisasterManagementSkill
from viki.skills.public_safety.emergency_response import EmergencyResponseSkill
from viki.skills.public_safety.fraud_detection import FraudDetectionSkill
from viki.skills.public_safety.government_services import GovernmentServicesSkill
from viki.skills.public_safety.investigation import InvestigationSkill
from viki.skills.public_safety.osint import OSINTResearchSkill
from viki.skills.public_safety.policy_research import PolicyResearchSkill
from viki.skills.public_safety.public_safety_education import PublicSafetyEducationSkill
from viki.skills.public_safety.viki_safety import VIKISafetyAgent

_SKILL_REGISTRY = {
    "investigation": InvestigationSkill,
    "cybercrime": CybercrimeAnalysisSkill,
    "fraud_detection": FraudDetectionSkill,
    "government_services": GovernmentServicesSkill,
    "emergency_response": EmergencyResponseSkill,
    "public_safety_education": PublicSafetyEducationSkill,
    "disaster_management": DisasterManagementSkill,
    "osint": OSINTResearchSkill,
    "policy_research": PolicyResearchSkill,
    "citizen_assistance": CitizenAssistanceSkill,
    "viki_safety": VIKISafetyAgent,
}

_AGENT_REGISTRY = {
    "investigation": InvestigationAgent,
    "cybersecurity": CybersecurityAgent,
    "government": GovernmentAgent,
    "emergency": EmergencyAgent,
    "research": ResearchAgent,
    "viki_safety": SafetyAgent,
}
from viki.skills.public_safety.config import SafetyConfig
from viki.skills.public_safety.memory import MemoryEntry, MemoryType, PublicSafetyMemory
from viki.skills.public_safety.nl_bridge import PublicSafetyNLBridge
from viki.skills.public_safety.viki_safety import VIKISafetyAgent


class PublicSafetyOrchestrator:
    """Single entry point for the entire public safety framework.

    Initializes and connects: skills, agents, NL bridge, auto-learning,
    memory, audit, and optional VIKIController integration.
    """

    def __init__(self, config: SafetyConfig | None = None):
        self.config = config or SafetyConfig.from_env()
        os.makedirs(self.config.data_dir, exist_ok=True)

        # --- Initialize subsystems ---
        self.memory = PublicSafetyMemory(
            storage_path=os.path.join(self.config.data_dir, "memory")
            if self.config.memory_enabled
            else None
        )
        self.audit = AuditStore(
            storage_path=os.path.join(self.config.data_dir, "audit")
            if self.config.audit_logging
            else None
        )
        self.auto_learning = get_auto_learning_engine(
            data_dir=os.path.join(self.config.data_dir, "learning")
        )
        if not self.config.auto_learning:
            self.auto_learning.disable()

        # --- Initialize skills ---
        self.skills: dict[str, BasePublicSafetySkill] = {
            name: cast("Callable[..., BasePublicSafetySkill]", cls)()
            for name, cls in _SKILL_REGISTRY.items()
        }
        self._wire_auto_learning_to_skills()

        # --- Initialize agents ---
        self.agent_coordinator = self._build_agent_coordinator()

        # --- Initialize NL bridge ---
        self.nl_bridge = self._build_nl_bridge()

    def _wire_auto_learning_to_skills(self):
        """Wire auto-learning into every skill that supports it."""
        if not self.config.auto_learning:
            return
        for skill in self.skills.values():
            if isinstance(skill, VIKISafetyAgent):
                skill.enable_auto_learning(self.auto_learning)

    def _build_agent_coordinator(self) -> AgentCoordinator:
        """Build coordinator with all agents, linking their skills."""
        coord = AgentCoordinator()

        agent_roles: list[tuple[str, BaseAgent]] = [
            ("investigation", InvestigationAgent()),
            ("cybersecurity", CybersecurityAgent()),
            ("government", GovernmentAgent()),
            ("emergency", EmergencyAgent()),
            ("research", ResearchAgent()),
            ("viki_safety", SafetyAgent()),
        ]

        skill_to_agent: dict[str, str] = {
            "investigation": "investigation",
            "cybercrime": "cybersecurity",
            "fraud_detection": "research",
            "government_services": "government",
            "emergency_response": "emergency",
            "public_safety_education": "research",
            "disaster_management": "emergency",
            "osint": "research",
            "policy_research": "government",
            "citizen_assistance": "government",
            "viki_safety": "research",
        }

        for agent_name, agent in agent_roles:
            for skill_name in _SKILL_REGISTRY:
                if agent_name == skill_to_agent.get(skill_name):
                    skill = self.skills.get(skill_name)
                    if skill:
                        agent.register_skill(skill)
            coord.register_agent(agent)

        return coord

    def _build_nl_bridge(self) -> PublicSafetyNLBridge:
        """Build the NL bridge with config settings."""
        from viki.core.model.local_llm import LocalLLM

        client = LocalLLM(
            {
                "base_url": self.config.llm_host,
                "model_name": self.config.model,
                "temperature": self.config.temperature,
            }
        )
        bridge = PublicSafetyNLBridge(
            llm_client=client,
            model=self.config.model,
            auto_learn=self.config.auto_learning,
        )
        if self.config.auto_learning:
            viki_safety = self.skills.get("viki_safety")
            if isinstance(viki_safety, VIKISafetyAgent):
                viki_safety.enable_auto_learning(self.auto_learning)
        return bridge

    # --- Public API ---

    async def process(self, query: str, context: dict[str, Any] | None = None) -> str:
        """Process a natural language query through the NL bridge.

        Automatically learns from results and stores in memory + audit.
        """
        async with AuditContextManager(
            self.audit, "orchestrator", "process", session_id=query[:64]
        ):
            context = context or {}
            context["_orchestrator"] = self

            result = await self.nl_bridge.process(query, context)

            self.memory.store(
                MemoryEntry(
                    type=MemoryType.SHORT_TERM,
                    content={"query": query, "response": result[:500]},
                    tags=["nl_query"],
                    source="orchestrator",
                )
            )

            return result

    async def analyze_threat(self, content: str, **kwargs) -> SkillResult:
        """Directly analyze a threat bypassing NL — uses the VIKI Safety skill."""
        viki = self.skills.get("viki_safety")
        if not viki:
            return SkillResult(
                skill_name="viki_safety", success=False, error="VIKI Safety skill not loaded"
            )
        return await viki.execute({"content": content, **kwargs})

    async def coordinate(self, query: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Coordinate multiple agents for complex multi-domain queries.

        Returns structured results from all relevant agents.
        """
        result = await self.agent_coordinator.execute(query, context)
        return result.to_dict()

    async def learn(
        self, threat_summary: str, threat_type: str = "manual", **details
    ) -> dict[str, Any]:
        """Explicitly teach the system about a new threat pattern."""
        return self.auto_learning.remember_threat(
            summary=threat_summary,
            threat_type=threat_type,
            risk_level=details.get("risk_level", "low"),
            evidence_patterns=details.get("evidence_patterns", []),
            detection_success=details.get("detection_success", True),
        ).to_dict()

    def get_insights(self) -> dict[str, Any]:
        """Get learning insights, statistics, and suggestions."""
        return self.auto_learning.get_statistics()

    def get_audit_log(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent audit events."""
        return [e.to_dict() for e in self.audit.get_recent(limit)]

    def get_threat_memory(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent threat memories."""
        return [m.to_dict() for m in self.auto_learning.get_recent_threats(limit)]

    # --- Controller Integration ---

    def connect_controller(self, controller) -> dict[str, Any]:
        """Connect to a VIKIController instance.

        Registers all skills in the controller's skill registry and
        connects the auto-learning engine to the controller's LearningModule.
        """
        connected: dict[str, Any] = {"skills": [], "learning": False}

        if hasattr(controller, "skill_registry"):
            reg = controller.skill_registry
            for name, skill in self.skills.items():
                if not reg.get_skill(name):
                    reg.register_skill(skill)
                    connected["skills"].append(name)

        if hasattr(controller, "learning"):
            self.auto_learning.connect_controller(controller.learning)
            connected["learning"] = True

        return connected

    # --- System Health ---

    def health_check(self) -> dict[str, Any]:
        """Get health status of all subsystems."""
        return {
            "orchestrator": True,
            "skills_loaded": len(self.skills),
            "skill_names": list(self.skills.keys()),
            "agents_loaded": len(self.agent_coordinator.list_agents()),
            "auto_learning": self.auto_learning.enabled,
            "auto_learning_stats": {
                "patterns": len(self.auto_learning._patterns),
                "threats": len(self.auto_learning._threat_memories),
            },
            "memory": self.config.memory_enabled,
            "audit": self.config.audit_logging,
            "model": self.config.model,
            "config": self.config.to_dict(),
        }


# Global singleton for easy access
_orchestrator: PublicSafetyOrchestrator | None = None


def get_orchestrator(config: SafetyConfig | None = None) -> PublicSafetyOrchestrator:
    """Get or create the global orchestrator singleton."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = PublicSafetyOrchestrator(config)
    return _orchestrator

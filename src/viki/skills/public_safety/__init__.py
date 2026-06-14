"""
Public Safety, Investigation, and Government Assistance Skills Framework.

A modular, ethical, and privacy-focused skill system for AI-assisted
public safety, investigation, and government services.
"""

from __future__ import annotations

from .agents import (
    AgentCoordinator,
    CybersecurityAgent,
    EmergencyAgent,
    GovernmentAgent,
    InvestigationAgent,
    ResearchAgent,
)
from .agents import (
    VIKISafetyAgent as SafetyAgent,
)
from .base import (
    AuditLogger,
    BasePublicSafetySkill,
    CapabilityDefinition,
    ConfidenceScore,
    ConfidenceScorer,
    InputValidator,
    ReasoningEngine,
    ReportingEngine,
    SafetyCheckResult,
    SafetyRules,
    SkillResult,
)
from .citizen_assistance import CitizenAssistanceSkill
from .config import SafetyConfig
from .cybercrime import CybercrimeAnalysisSkill
from .disaster_management import DisasterManagementSkill
from .emergency_response import EmergencyResponseSkill
from .fraud_detection import FraudDetectionSkill
from .government_services import GovernmentServicesSkill
from .investigation import InvestigationSkill
from .memory import MemoryType, PublicSafetyMemory
from .nl_bridge import PublicSafetyNLBridge
from .orchestrator import PublicSafetyOrchestrator, get_orchestrator
from .osint import OSINTResearchSkill
from .policy_research import PolicyResearchSkill
from .public_safety_education import PublicSafetyEducationSkill
from .viki_safety import VIKISafetyAgent

__all__ = [
    "BasePublicSafetySkill",
    "CapabilityDefinition",
    "InputValidator",
    "SafetyRules",
    "ReasoningEngine",
    "ReportingEngine",
    "ConfidenceScorer",
    "AuditLogger",
    "SkillResult",
    "SafetyCheckResult",
    "ConfidenceScore",
    "InvestigationSkill",
    "CybercrimeAnalysisSkill",
    "FraudDetectionSkill",
    "GovernmentServicesSkill",
    "EmergencyResponseSkill",
    "PublicSafetyEducationSkill",
    "DisasterManagementSkill",
    "OSINTResearchSkill",
    "PolicyResearchSkill",
    "CitizenAssistanceSkill",
    "VIKISafetyAgent",
    "PublicSafetyNLBridge",
    "PublicSafetyMemory",
    "MemoryType",
    "SafetyConfig",
    "PublicSafetyOrchestrator",
    "get_orchestrator",
    "InvestigationAgent",
    "CybersecurityAgent",
    "GovernmentAgent",
    "EmergencyAgent",
    "ResearchAgent",
    "SafetyAgent",
    "AgentCoordinator",
    "SKILL_REGISTRY",
    "AGENT_REGISTRY",
    "get_skill",
    "get_agent",
    "list_skills",
    "list_agents",
]

SKILL_REGISTRY = {
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

AGENT_REGISTRY = {
    "investigation": InvestigationAgent,
    "cybersecurity": CybersecurityAgent,
    "government": GovernmentAgent,
    "emergency": EmergencyAgent,
    "research": ResearchAgent,
    "viki_safety": SafetyAgent,
}


def get_skill(skill_name: str) -> type[BasePublicSafetySkill] | None:
    """Get a skill class by name."""
    return SKILL_REGISTRY.get(skill_name)


def get_agent(agent_name: str):
    """Get an agent class by name."""
    return AGENT_REGISTRY.get(agent_name)


def list_skills() -> list[str]:
    """List all available skill names."""
    return list(SKILL_REGISTRY.keys())


def list_agents() -> list[str]:
    """List all available agent names."""
    return list(AGENT_REGISTRY.keys())

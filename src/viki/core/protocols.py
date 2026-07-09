"""
ControllerProto — typed protocol for mixin ``self`` attributes.

Every mixin that accesses ``self.<attribute>`` declares its dependency here
so mypy can check that the concrete ``VIKIController`` satisfies the contract.
"""

from __future__ import annotations

from typing import Any, Protocol

from viki.api.central_nexus import MessagingNexus
from viki.application.services.forge_orchestrator import ForgeOrchestrator
from viki.application.services.safety_service import SafetyService
from viki.application.services.swarm_orchestrator import SwarmOrchestrator
from viki.core.audio_gateway import VoiceModule
from viki.core.autonomous_monitor import WatchdogModule, WellnessPulse
from viki.core.biometric_service import BioModule
from viki.core.capabilities import CapabilityRegistry
from viki.core.cognitive_loop import CognitiveRouter, RouterTelemetry
from viki.core.config_watcher import ConfigWatcher
from viki.core.continuous_learning import ContinuousLearner
from viki.core.deliberation import DeliberationEngine
from viki.core.endpoint_guard import EndpointGuardService
from viki.core.event_bus import CognitiveSignals
from viki.core.filesystem_v2 import SemanticFS
from viki.core.governor import EthicalGovernor
from viki.core.identity_profile import Soul
from viki.core.knowledge_gaps import KnowledgeGapDetector
from viki.core.knowledge_ingestion import LearningModule
from viki.core.layers import ConsciousnessStack
from viki.core.memory import HierarchicalMemory
from viki.core.meta_cognition import ReflectorModule
from viki.core.mission_control import MissionControl
from viki.core.model import ModelRouter
from viki.core.output_verifier import JudgmentEngine
from viki.core.performance_benchmark import ControlledBenchmark
from viki.core.rapid_response_system import ReflexBrain
from viki.core.runtime_health import RuntimeHealthReporter
from viki.core.scorecard import IntelligenceScorecard
from viki.core.security_guard import SafetyLayer
from viki.core.self_critique import SelfCritique
from viki.core.self_healer import SelfHealer
from viki.core.self_model import SelfModel
from viki.core.super_admin import SuperAdminLayer
from viki.core.variant_optimizer import ModelABTest
from viki.core.world import WorldModel
from viki.service_registry import Container
from viki.skills.registry import SkillRegistry


class ControllerProto(Protocol):
    """The subset of ``VIKIController`` attributes that mixins depend on."""

    soul: Soul
    model_router: ModelRouter
    router_telemetry: RouterTelemetry
    cognitive_router: CognitiveRouter
    deliberation_engine: DeliberationEngine
    reflex_brain: ReflexBrain
    consciousness_stack: ConsciousnessStack
    hierarchical_memory: HierarchicalMemory
    working_memory: HierarchicalMemory
    learning_module: LearningModule
    knowledge_gap_detector: KnowledgeGapDetector
    skill_registry: SkillRegistry
    mission_control: MissionControl
    signals: CognitiveSignals
    ethical_governor: EthicalGovernor
    safety_layer: SafetyLayer
    security_guard: SafetyLayer
    judgment_engine: JudgmentEngine
    self_critique: SelfCritique
    self_model: SelfModel
    reflector_module: ReflectorModule
    continuous_learner: ContinuousLearner
    semantic_fs: SemanticFS
    world_model: WorldModel
    task_planner: Any
    specialist_agent: Any
    super_admin: SuperAdminLayer
    self_healer: SelfHealer
    voice_module: VoiceModule
    bio_module: BioModule
    watchdog: WatchdogModule
    wellness_pulse: WellnessPulse
    endpoint_guard: EndpointGuardService
    config_watcher: ConfigWatcher
    capability_registry: CapabilityRegistry
    runtime_health: RuntimeHealthReporter
    messaging_nexus: MessagingNexus
    forge_orchestrator: ForgeOrchestrator
    swarm_orchestrator: SwarmOrchestrator
    safety_service: SafetyService
    scorecard: IntelligenceScorecard
    model_ab_test: ModelABTest
    telemetry_service: Any
    benchmark: ControlledBenchmark
    container: Container
    config: dict[str, Any]
    system_settings: dict[str, Any]
    loop: Any
    session_id: str
    debug: bool
    admin_mode: bool

    async def process_request(
        self,
        user_input: str,
        on_event: Any = None,
        on_think: Any = None,
        attachment_paths: list[str] | None = None,
        session_id: str | None = None,
    ) -> str: ...

    def track_touched_item(self, category: str, item: str) -> None: ...

import asyncio
import os
import time
from typing import Any

from viki.api.central_nexus import MessagingNexus
from viki.application.services.forge_orchestrator import ForgeOrchestrator
from viki.config.logger import viki_logger
from viki.core.audio_gateway import VoiceModule
from viki.core.autonomous_monitor import WatchdogModule, WellnessPulse
from viki.core.biometric_service import BioModule
from viki.core.branch_manager import BranchManager
from viki.core.capabilities import CapabilityRegistry
from viki.core.cognitive_loop import CognitiveRouter, RouterTelemetry
from viki.core.config_watcher import ConfigWatcher
from viki.core.continuous_learning import ContinuousLearner
from viki.core.controller.controller_lifecycle import LifecycleMixin
from viki.core.controller.controller_pipeline import PipelineMixin
from viki.core.controller.controller_skills import SkillsMixin
from viki.core.controller.controller_telemetry import TelemetryMixin
from viki.core.controller.controller_validation import ValidationMixin
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
from viki.core.orchestrator_helpers import (
    _LAZY_SKILL_SPECS,
    _build_env_nested_overrides,
    _build_env_overrides,
    load_yaml,
    persona_from_soul_path,
    read_json,
    read_text_truncated,
    write_json,
)
from viki.core.output_verifier import JudgmentEngine
from viki.core.performance_benchmark import ControlledBenchmark
from viki.core.rapid_response_system import ReflexBrain
from viki.core.request_pipeline import build_default_preflight_pipeline
from viki.core.runtime_health import RuntimeHealthReporter
from viki.core.scorecard import IntelligenceScorecard
from viki.core.security_guard import SafetyLayer
from viki.core.self_model import SelfModel
from viki.core.state_consolidation import DreamModule
from viki.core.super_admin import SuperAdminLayer
from viki.core.telemetry import TelemetryStore
from viki.core.temporal_memory import TimeTravelModule
from viki.core.test_healer import TestHealerPipeline
from viki.core.tool_contract import ToolContractValidator
from viki.core.variant_optimizer import ModelABTest
from viki.core.world import WorldModel
from viki.ops.tenant_ops import SimpleOpsPlanner
from viki.skills.registry import SkillRegistry


class VIKIController(
    LifecycleMixin,
    SkillsMixin,
    PipelineMixin,
    ValidationMixin,
    TelemetryMixin,
):
    # Centralize default paths/tokens to avoid duplicated literals and keep behavior consistent.
    DEFAULT_DATA_DIR = "./data"
    DEFAULT_WORKSPACE_DIR = "."
    CONFIRM_TOKEN = "/confirm"
    REJECT_TOKEN = "/reject"

    # Skill execution timeout: min/max bounds and default budget multiplier
    SKILL_TIMEOUT_MAX = 120
    SKILL_TIMEOUT_MIN = 30
    SKILL_TIMEOUT_BUDGET_DEFAULT = 5
    SKILL_TIMEOUT_BUDGET_MULTIPLIER = 12

    _LAZY_SKILL_SPECS = _LAZY_SKILL_SPECS  # imported from orchestrator_helpers

    def _write_json(self, path: str, payload: Any, indent: int | None = None) -> None:
        write_json(path, payload, indent)

    def _read_json(self, path: str) -> Any:
        return read_json(path)

    def _read_text_truncated(self, path: str, max_len: int) -> str:
        return read_text_truncated(path, max_len)

    def _apply_system_overrides(
        self, system: dict[str, Any], workspace_override: str | None
    ) -> None:
        system.update(_build_env_overrides())
        for section, values in _build_env_nested_overrides().items():
            existing = self.settings.setdefault(section, {})
            if not isinstance(existing, dict):
                existing = {}
                self.settings[section] = existing
            existing.update(values)
        if workspace_override:
            system["workspace_dir"] = os.path.abspath(workspace_override)

    def _resolve_models_config(self) -> None:
        models_conf_rel = self.settings.get("models_config", "./config/models.yaml")
        if models_conf_rel.startswith("./"):
            models_conf_rel = models_conf_rel[2:]
        settings_dir = os.path.dirname(os.path.abspath(self.settings_path))
        self.models_config_path = os.path.join(settings_dir, models_conf_rel)
        self.models_config = self._load_yaml(self.models_config_path)

    def _resolve_security_layer_path(self) -> None:
        if "security_layer_path" not in self.settings:
            return
        sec_path = self.settings["security_layer_path"]
        if sec_path.startswith("./"):
            sec_path = sec_path[2:]
        settings_dir = os.path.dirname(os.path.abspath(self.settings_path))
        candidate = os.path.join(settings_dir, sec_path)
        if not os.path.exists(candidate):
            candidate_viki = os.path.join(settings_dir, "..", "viki", sec_path)
            if os.path.exists(candidate_viki):
                candidate = candidate_viki
        self.settings["security_layer_path"] = candidate

    def _load_yaml(self, path: str) -> dict[str, Any]:
        return load_yaml(path)

    def _persona_from_soul_path(self, soul_path: str) -> str:
        return persona_from_soul_path(soul_path)

    def __init__(self, settings_path: str, soul_path: str, workspace_override: str | None = None):
        self.settings_path = settings_path
        self.settings = self._load_yaml(settings_path)
        self.soul_path = soul_path
        # Overlay environment variables so users can configure via .env without editing YAML
        system = self.settings.setdefault("system", {})
        self._apply_system_overrides(system, workspace_override)
        self._init_db()
        self.shadow_mode = bool(self.settings.get("system", {}).get("shadow_mode", False))
        self.air_gap = bool(self.settings.get("system", {}).get("air_gap", False))
        self.low_resource_mode = bool(
            self.settings.get("system", {}).get("low_resource_mode", False)
        )

        # Security session history for CLI dashboard
        self.session_history: dict[str, list[str]] = {
            "touched_files": [],
            "executed_commands": [],
            "blocked_actions": [],
        }

        # 0. Fast Perception Layer (Reflex Brain)
        data_dir = system.get("data_dir", self.DEFAULT_DATA_DIR)
        self.reflex = ReflexBrain(data_dir=data_dir)

        # Global Interrupt Token (Shared Presence)
        self.interrupt_signal = asyncio.Event()

        # Background loop shutdown signal (allows clean termination of infinite loops)
        self._shutdown_event = asyncio.Event()

        # Task tracking for proper cleanup
        self._background_tasks: set[Any] = set()
        self.is_agent_mode = False
        self.is_plan_mode = False
        self.is_debug_mode = False
        self.is_singularity_mode = False

        # --- SECURITY FIX: HIGH-005 - Recursion depth tracking ---
        self._reflex_recursion_depth = 0
        self._max_reflex_recursion = 3

        self._resolve_models_config()
        self._resolve_security_layer_path()

        # v26.1: High-scale Distributed Traceability & Self-Healing
        self.telemetry = TelemetryStore(data_dir)
        self.test_healer = TestHealerPipeline(self)

        self.soul = Soul(soul_path)
        self.persona = self._persona_from_soul_path(soul_path)

        # Merge owner profile from settings into soul.config so cortex can
        # reference it in every deliberation prompt.
        _owner = self.settings.get("system", {}).get("owner", {})
        if _owner and isinstance(_owner, dict):
            self.soul.config["owner"] = _owner
            # Build a concise identity string and prepend to system_prompt
            _name = _owner.get("name", "")
            _role = _owner.get("role", "")
            _loc = _owner.get("location", "")
            _ctx = _owner.get("custom_context", "")
            _interests = ", ".join(_owner.get("interests", []))
            _owner_block = (
                f"[MANDATORY OVERRIDE — OPERATOR CONFIGURATION]\n"
                f"The following identity and behavioral instructions are set by the system owner and MUST be followed at all times. "
                f"They override any default assumptions about who the user is or how you should behave.\n\n"
                f"OPERATOR NAME: {_name}\n"
                + (f"OPERATOR ROLE: {_role}\n" if _role else "")
                + (f"OPERATOR LOCATION: {_loc}\n" if _loc else "")
                + (f"OPERATOR INTERESTS: {_interests}\n" if _interests else "")
                + (f"\nBEHAVIORAL MANDATE:\n{_ctx}\n" if _ctx else "")
                + f"\nYou MUST address the operator as '{_name}' and fully adopt the behavioral mandate above. "
                f"Do NOT revert to any prior assumptions about the operator's identity.\n"
                f"[END MANDATORY OVERRIDE]\n"
            )
            _base_prompt = self.soul.config.get(
                "system_prompt",
                "You are VIKI, a helpful and friendly AI assistant.",
            )
            self.soul.config["system_prompt"] = _owner_block + "\n" + _base_prompt

        self.safety = SafetyLayer(self.settings)
        self.nexus = MessagingNexus(request_processor=self)

        self.learning = LearningModule(data_dir)

        # v25: Knowledge Gap Detection
        self.knowledge_gaps = KnowledgeGapDetector(self.learning)

        # v25: A/B Testing and Continuous Learning
        self.ab_tester = ModelABTest(self)
        self.continuous_learner = ContinuousLearner(self)

        # v23: Hierarchical Memory Stack (Orythix Standard)
        self.memory = HierarchicalMemory(self.settings, learning_module=self.learning)

        self.voice_module = VoiceModule()

        # Resolve admin.yaml relative to settings directory
        config_dir = os.path.dirname(os.path.abspath(settings_path))
        admin_path = os.path.join(config_dir, "admin.yaml")
        if not os.path.exists(admin_path):
            viki_logger.warning(f"Admin config not found at {admin_path}, using default.")

        self.super_admin = SuperAdminLayer(admin_path)
        self.air_gap = self.settings.get("system", {}).get("air_gap", False)
        self.shadow_mode = self.settings.get("system", {}).get("shadow_mode", False)
        self.local_llm_only = self.settings.get("system", {}).get("local_llm_only", True)

        # Level 6 Modules
        self.sfs = SemanticFS(
            self.settings.get("system", {}).get("workspace_dir", self.DEFAULT_WORKSPACE_DIR)
        )
        self.history = TimeTravelModule(data_dir)
        self.branch_manager = BranchManager(os.path.join(data_dir, "branches.db"))

        try:
            from viki.core.usage_log import configure_session_usage_log

            configure_session_usage_log(
                data_dir,
                bool(self.settings.get("system", {}).get("session_usage_log", True)),
            )
        except Exception:
            viki_logger.warning("failed to configure session usage log")

        # Phase 1: Budget enforcement for cloud calls (daily/per-call cost cap + circuit breaker).
        from viki.core.resource_budget import LLMBudget

        budget_state_path = os.path.join(
            data_dir,
            "llm_budget.json",
        )
        self.llm_budget = LLMBudget(state_path=budget_state_path)

        self.model_router = ModelRouter(
            self.models_config_path,
            air_gap=self.air_gap,
            local_llm_only=self.local_llm_only,
            budget=self.llm_budget,
            system_settings=self.settings,
        )
        if getattr(self.model_router, "_budget_config", None):
            self.llm_budget.config.update(self.model_router._budget_config)

        self.skill_registry = SkillRegistry()
        self.tool_contract = ToolContractValidator(self.skill_registry, self.safety)
        self.health_reporter = RuntimeHealthReporter(self)
        self.capabilities = CapabilityRegistry()
        self.disabled_skills: dict[Any, Any] = {}
        self._register_default_skills()

        # Phase 7 (P0): MCP integration.
        self.mcp_client = None
        self.mcp_skill_count = 0
        self.sub_agents: dict[str, Any] = {}
        try:
            from viki.core.telemetry_service import init_persistent_traces

            init_persistent_traces(os.path.join(data_dir, "traces.db"))
        except Exception as e:
            viki_logger.debug("init_persistent_traces failed: %s", e)
        self.active_tasks: list[Any] = []
        self.pending_actions: dict[Any, Any] = {}
        self.pending_ops_plans: dict[Any, Any] = {}
        self._last_response_meta_by_session: dict[Any, Any] = {}
        self._session_llm_usage: dict[str, dict[str, Any]] = {}

        # Point 4: Cognitive Budget Allocator
        self.budgets = {
            "vision": {"time": 10.0, "tokens": 2048, "risk": 0.2, "model": "vision-capable"},
            "coding": {"time": 15.0, "tokens": 4096, "risk": 0.5, "model": "pro-coder"},
            "reasoning": {"time": 8.0, "tokens": 1024, "risk": 0.1, "model": "heavy-thinker"},
            "general": {"time": 5.0, "tokens": 512, "risk": 0.1, "model": "chatter"},
        }

        # v9-v10 Digital Cognitive Organism State
        self.signals = CognitiveSignals()
        self.world = WorldModel(data_dir)
        self.cortex = ConsciousnessStack(
            self.model_router,
            soul_config=self.soul.config,
            skill_registry=self.skill_registry,
            world_model=self.world,
            data_dir=data_dir,
        )

        # v11: Intelligence Governance (Judgment Engine)
        self.judgment = JudgmentEngine(self.learning, self.budgets)
        self.router_telemetry = RouterTelemetry()
        self.cognitive_router = CognitiveRouter(
            self.reflex, self.judgment, telemetry=self.router_telemetry, data_dir=data_dir
        )
        self.scorecard = IntelligenceScorecard(data_dir)

        # v25: Adaptive Self-Modification (Evolution Engine)
        from viki.core.evolution import EvolutionEngine

        self.evolution = EvolutionEngine(data_dir)
        self.evolution.set_reflex_module(self.reflex)

        # v26: Context Retriever (RAG)
        from viki.core.utils.context_retriever import ContextRetriever

        _ws_dir = system.get("workspace_dir", self.DEFAULT_WORKSPACE_DIR)
        self.context_retriever = ContextRetriever(_ws_dir)
        self.evolution.set_model_router(self.model_router)
        self.evolution.set_skill_registry(self.skill_registry)

        self.benchmark = ControlledBenchmark(self)

        # v26: Planner/Executor Split (The "Nervous System")
        from viki.core.task_planner import PlannerExecutor

        self.planner = PlannerExecutor(self.model_router)

        # v26: Tenant-aware Ops planner
        self.ops_planner = SimpleOpsPlanner(self)
        self.forge_orchestrator = ForgeOrchestrator(self)

        self.safe_mode = False
        self.internal_trace: list[Any] = []
        self.last_interaction_time = time.time()
        self.interaction_pace = "Standard"

        # Proactive & Meta-Cognition Modules
        self.watchdog = WatchdogModule(self)
        self.wellness = WellnessPulse(self)
        self.reflector = ReflectorModule(self)
        bio_settings = self.settings.get("system", {})
        bio_backend = (
            os.environ.get("VIKI_BIO_BACKEND") or bio_settings.get("bio_backend") or "stub"
        )
        self.bio = BioModule(
            webcam_enabled=bool(bio_settings.get("bio_webcam_enabled", False)),
            backend=bio_backend,
            analysis_interval_s=float(bio_settings.get("bio_analysis_interval_s", 10.0)),
        )
        self.dream = DreamModule(self)
        self.endpoint_guard = EndpointGuardService(self)

        # v13: Autonomous Startup Pulse
        _skip_pulse = os.environ.get("VIKI_SKIP_STARTUP_PULSE", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        if _skip_pulse:
            viki_logger.info(
                "VIKI_SKIP_STARTUP_PULSE: startup pulse disabled (headless / scheduled worker)."
            )
        elif not getattr(self, "low_resource_mode", False):
            try:
                asyncio.get_running_loop()
                self._create_tracked_task(self._startup_pulse(), "startup_pulse")
            except RuntimeError:
                viki_logger.debug("Sync Mode: Startup Pulse deferred (no running loop).")
        else:
            viki_logger.debug("Startup pulse suppressed by low_resource_mode.")

        # Background model pre-warm
        prewarm_enabled = (
            self.settings.get("system", {}).get("prewarm_default_model", True)
            and not getattr(self, "low_resource_mode", False)
            and not getattr(self, "air_gap", False)
        )
        if prewarm_enabled:
            try:
                asyncio.get_running_loop()
                self._create_tracked_task(self._prewarm_default_model(), "model_prewarm")
            except RuntimeError:
                viki_logger.debug("Sync Mode: Model prewarm deferred (no running loop).")

        # --- ORYTHIX COGNITIVE ARCHITECTURE (v22 Evolution) ---
        self.governor = EthicalGovernor()
        self.self_model = SelfModel(governor=self.governor)
        self.narrative = self.memory.episodic
        self.deliberation = DeliberationEngine(llm=self.model_router, self_model=self.self_model)

        # Phase 6: Autonomy
        self.mission_control = MissionControl(
            request_processor=self,
            system_settings=self.settings.get("system", {}),
            signals=self.signals,
        )
        self._preflight_pipeline = build_default_preflight_pipeline()

        try:
            self.endpoint_guard.start_watcher()
        except Exception as e:
            viki_logger.debug("endpoint_guard init: %s", e)

        # Config hot-reload via watchdog (non-blocking).
        self.config_watcher = ConfigWatcher(callback=self._on_config_file_changed)
        if not getattr(self, "low_resource_mode", False):
            try:
                config_dir = os.path.dirname(os.path.abspath(settings_path))
                settings_file = os.path.join(config_dir, "settings.yaml")
                models_file = os.path.join(config_dir, "models.yaml")
                self.config_watcher.start(settings_file, models_file)
            except Exception as e:
                viki_logger.debug("config_watcher start: %s", e)

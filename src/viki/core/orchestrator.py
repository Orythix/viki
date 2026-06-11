import asyncio
import importlib
import os
import re
import time
from typing import Any

from viki.api.central_nexus import MessagingNexus
from viki.application.services.forge_orchestrator import ForgeOrchestrator
from viki.config.logger import viki_logger
from viki.core import command_handlers
from viki.core.audio_gateway import VoiceModule
from viki.core.autonomous_monitor import WatchdogModule, WellnessPulse
from viki.core.biometric_service import BioModule
from viki.core.capabilities import CapabilityRegistry
from viki.core.cognitive_loop import CognitiveRouter, RouterTelemetry
from viki.core.cognitive_processor import ConsciousnessStack
from viki.core.config_watcher import ConfigWatcher
from viki.core.continuous_learning import ContinuousLearner
from viki.core.deliberation import DeliberationEngine
from viki.core.endpoint_guard import EndpointGuardService
from viki.core.event_bus import CognitiveSignals
from viki.core.filesystem_v2 import SemanticFS
from viki.core.git_context import get_git_workspace_snapshot

# Orythix Cognitive Subsystems
from viki.core.governor import EthicalGovernor
from viki.core.identity_profile import Soul
from viki.core.inference_gateway import ModelRouter
from viki.core.knowledge_gaps import KnowledgeGapDetector
from viki.core.knowledge_ingestion import LearningModule
from viki.core.memory import HierarchicalMemory
from viki.core.meta_cognition import ReflectorModule

# Phase 6: Autonomy
from viki.core.mission_control import MissionControl
from viki.core.orchestrator_helpers import (
    json_type_matches,
    load_yaml,
    persona_from_soul_path,
    read_json,
    read_text_truncated,
    write_json,
)
from viki.core.output_verifier import JudgmentEngine
from viki.core.performance_benchmark import ControlledBenchmark
from viki.core.rapid_response_system import ReflexBrain
from viki.core.react_loop import run_react_loop
from viki.core.request_pipeline import RequestContext, build_default_preflight_pipeline
from viki.core.schema import VIKIResponse
from viki.core.scorecard import IntelligenceScorecard
from viki.core.security_guard import SafetyLayer, safe_for_log
from viki.core.self_model import SelfModel
from viki.core.state_consolidation import DreamModule
from viki.core.super_admin import SuperAdminLayer
from viki.core.telemetry import TelemetryStore
from viki.core.telemetry_service import close_persistent_traces
from viki.core.temporal_memory import TimeTravelModule
from viki.core.test_healer import TestHealerPipeline
from viki.core.variant_optimizer import ModelABTest
from viki.core.world import WorldModel
from viki.ops.tenant_ops import ControllerTenantConnector, OpsPlan, SimpleOpsPlanner
from viki.skills.registry import SkillRegistry


class VIKIController:
    # Centralize default paths/tokens to avoid duplicated literals and keep behavior consistent.
    DEFAULT_DATA_DIR = "./data"
    DEFAULT_WORKSPACE_DIR = "."
    CONFIRM_TOKEN = "/confirm"
    REJECT_TOKEN = "/reject"

    def _write_json(self, path: str, payload: Any, indent: int | None = None) -> None:
        write_json(path, payload, indent)

    def _read_json(self, path: str) -> Any:
        return read_json(path)

    def _read_text_truncated(self, path: str, max_len: int) -> str:
        return read_text_truncated(path, max_len)

    def _apply_system_overrides(
        self, system: dict[str, Any], workspace_override: str | None
    ) -> None:
        """Apply env/YAML overrides to the `system` settings dict."""
        if os.environ.get("VIKI_DATA_DIR"):
            system["data_dir"] = os.path.abspath(os.path.expanduser(os.environ["VIKI_DATA_DIR"]))
        if os.environ.get("VIKI_WORKSPACE_DIR"):
            system["workspace_dir"] = os.path.abspath(
                os.path.expanduser(os.environ["VIKI_WORKSPACE_DIR"])
            )
        if os.environ.get("VIKI_PERSONA"):
            system["persona"] = os.environ.get("VIKI_PERSONA", "").strip()
        if workspace_override:
            system["workspace_dir"] = os.path.abspath(workspace_override)

        # Shadow mode and air gap from env (optional)
        if os.environ.get("VIKI_SHADOW_MODE", "").lower() in ("1", "true", "yes"):
            system["shadow_mode"] = True
        if os.environ.get("VIKI_AIR_GAP", "").lower() in ("1", "true", "yes"):
            system["air_gap"] = True
        if os.environ.get("VIKI_LOCAL_LLM_ONLY") is not None:
            system["local_llm_only"] = os.environ.get(
                "VIKI_LOCAL_LLM_ONLY", ""
            ).strip().lower() in (
                "1",
                "true",
                "yes",
            )
        if os.environ.get("VIKI_GIT_CONTEXT", "").lower() in ("1", "true", "yes"):
            system["git_workspace_context"] = True
        if os.environ.get("VIKI_LOW_RESOURCE", "").lower() in ("1", "true", "yes"):
            system["low_resource_mode"] = True

        if os.environ.get("VIKI_SESSION_USAGE_LOG") is not None:
            raw = os.environ.get("VIKI_SESSION_USAGE_LOG", "").strip().lower()
            system["session_usage_log"] = raw in ("1", "true", "yes")

        if os.environ.get("VIKI_AUTO_WEB_RESEARCH") is not None:
            raw = os.environ.get("VIKI_AUTO_WEB_RESEARCH", "").strip().lower()
            system["auto_web_research_when_uncertain"] = raw in ("1", "true", "yes", "on")

        if os.environ.get("VIKI_LESSON_EXPORT_MIN_ACCESS") is not None:
            raw = os.environ.get("VIKI_LESSON_EXPORT_MIN_ACCESS", "").strip()
            try:
                system["lesson_export_min_access_count"] = max(1, int(raw))
            except ValueError:
                pass

        if os.environ.get("VIKI_ENDPOINT_GUARD") is not None:
            raw = os.environ.get("VIKI_ENDPOINT_GUARD", "").strip().lower()
            eg = self.settings.setdefault("endpoint_guard", {})
            if not isinstance(eg, dict):
                eg = {}
                self.settings["endpoint_guard"] = eg
            if raw in ("1", "true", "yes", "on"):
                eg["enabled"] = True
                eg.setdefault("auto_start_watcher", True)
            elif raw in ("0", "false", "no", "off"):
                eg["enabled"] = False

        if os.environ.get("VIKI_BACKGROUND_EVOLUTION_AT_BOOT") is not None:
            raw = os.environ.get("VIKI_BACKGROUND_EVOLUTION_AT_BOOT", "").strip().lower()
            forge = self.settings.setdefault("forge", {})
            if not isinstance(forge, dict):
                forge = {}
                self.settings["forge"] = forge
            forge["background_evolution_at_boot"] = raw in ("1", "true", "yes", "on")

        # Bio webcam: unset = keep YAML default; explicit 0/1 overrides
        if os.environ.get("VIKI_BIO_WEBCAM") is not None:
            system["bio_webcam_enabled"] = os.environ.get(
                "VIKI_BIO_WEBCAM", ""
            ).strip().lower() in (
                "1",
                "true",
                "yes",
            )

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

    def _check_integration_credentials(
        self,
        cfg: dict[str, Any],
        env_var: str,
        integration_label: str,
        credentials_hint: str,
    ) -> None:
        if not cfg.get("enabled"):
            return
        path = cfg.get("credentials_path") or os.environ.get(env_var)
        if not path or not os.path.isfile(path):
            viki_logger.warning(
                f"Skill health: {integration_label} is enabled but credentials file not found. {credentials_hint}."
            )

    def _apply_skill_aliases(self) -> None:
        alias_pairs = [
            ("look", "look_at_screen"),
            ("highlight", "draw_overlay"),
            ("focus", "mount_focus"),
            ("net_scan", "security_tools"),
            ("web_audit", "security_tools"),
            ("sniffer", "security_tools"),
            ("evolve", "internal_forge"),
            ("recall", "recall"),
            ("python", "python_interpreter"),
            ("search", "research"),
            ("read", "research"),
            ("say", "voice"),
            ("speak", "voice"),
            ("pause", "media_control"),
            ("play", "media_control"),
            ("media", "media_control"),
            ("volume", "media_control"),
            ("copy", "clipboard"),
            ("paste", "clipboard"),
            ("windows", "window_manager"),
            ("minimize", "window_manager"),
            ("maximize", "window_manager"),
            ("powershell", "shell"),
            ("messaging", "messaging"),
            ("clawdis", "messaging"),
            ("notify", "notification"),
            ("toast", "notification"),
            ("video", "short_video_agent"),
            ("short", "short_video_agent"),
            ("antivirus", "endpoint_guard"),
            ("cache", "cache_pilot"),
            ("weaver", "context_weaver"),
            ("trace", "mind_trace"),
            ("audit", "autonomous_auditor"),
            ("logs", "log_voyager"),
            ("mutation", "mutation_pilot"),
            ("market", "market_explorer"),
            ("mem", "memory"),
            ("sovereign", "memory"),
        ]
        for alias_name, target_name in alias_pairs:
            target = self.skill_registry.get_skill(target_name)
            if target is not None:
                self.skill_registry.skills[alias_name] = target

    def _should_skip_evolution(self, force: bool) -> bool:
        """Return True if evolution should be redirected/skipped."""
        return (not force) and self.scorecard.check_plateau()

    def _handle_plateau_redirect(self) -> None:
        viki_logger.warning("STOP RULE ACTIVATED: Intelligence scorecard indicates model plateau.")
        viki_logger.info("Redirecting evolution effort to Controller Logic and Memory Discipline.")
        for rec in self.skill_registry.get_refactor_recommendations():
            self.learning.save_lesson(f"CONTROLLER_EVOLUTION_ADVISE: {rec}")

    def _get_evolution_state_path(self) -> str:
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return os.path.join(root_dir, "viki", "data", "evolution_state.json")

    def _init_db(self):
        """Ensure core data directories exist."""
        system = self.settings.get("system", {})
        data_dir = system.get("data_dir", self.DEFAULT_DATA_DIR)
        os.makedirs(data_dir, exist_ok=True)
        workspace_dir = system.get("workspace_dir", self.DEFAULT_WORKSPACE_DIR)
        os.makedirs(workspace_dir, exist_ok=True)

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
        self.session_history = {"touched_files": [], "executed_commands": [], "blocked_actions": []}

        # 0. Fast Perception Layer (Reflex Brain)
        data_dir = system.get("data_dir", self.DEFAULT_DATA_DIR)
        self.reflex = ReflexBrain(data_dir=data_dir)

        # Global Interrupt Token (Shared Presence)
        self.interrupt_signal = asyncio.Event()

        # Background loop shutdown signal (allows clean termination of infinite loops)
        self._shutdown_event = asyncio.Event()

        # Task tracking for proper cleanup
        self._background_tasks = set()
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
            # Fallback or let SuperAdmin handle it if designed to

        self.super_admin = SuperAdminLayer(admin_path)
        self.air_gap = self.settings.get("system", {}).get("air_gap", False)
        self.shadow_mode = self.settings.get("system", {}).get("shadow_mode", False)
        self.local_llm_only = self.settings.get("system", {}).get("local_llm_only", True)

        # Level 6 Modules
        self.sfs = SemanticFS(
            self.settings.get("system", {}).get("workspace_dir", self.DEFAULT_WORKSPACE_DIR)
        )
        self.history = TimeTravelModule(data_dir)

        try:
            from viki.core.usage_log import configure_session_usage_log

            configure_session_usage_log(
                data_dir,
                bool(self.settings.get("system", {}).get("session_usage_log", True)),
            )
        except Exception:
            pass

        # Phase 1: Budget enforcement for cloud calls (daily/per-call cost cap + circuit breaker).
        from viki.core.resource_budget import LLMBudget

        budget_state_path = os.path.join(
            data_dir,
            "llm_budget.json",
        )
        # Initial budget config will be merged with the YAML's `models.budget` block in the router.
        self.llm_budget = LLMBudget(state_path=budget_state_path)

        self.model_router = ModelRouter(
            self.models_config_path,
            air_gap=self.air_gap,
            local_llm_only=self.local_llm_only,
            budget=self.llm_budget,
            system_settings=self.settings,
        )
        # Re-merge YAML budget config into the LLMBudget after _load_config picked it up.
        if getattr(self.model_router, "_budget_config", None):
            self.llm_budget.config.update(self.model_router._budget_config)

        self.skill_registry = SkillRegistry()
        self.capabilities = CapabilityRegistry()
        self.disabled_skills = {}
        self._register_default_skills()
        # Phase 7 (P0): MCP integration. We hold the client here; actual
        # connection happens in `attach_mcp_skills_sync()` which is called
        # at boot by API/main entry points (and tolerates missing SDK / config).
        self.mcp_client = None
        self.mcp_skill_count = 0
        # Phase 7 (P1): registry of live SubAgents so the API can list/cancel
        # them. Keys are SubAgent.id.
        self.sub_agents: dict[str, Any] = {}
        # Phase 7 (P1): persistent trace store with parent IDs for the
        # dashboard Gantt view. Failure is non-fatal.
        try:
            from viki.core.telemetry_service import init_persistent_traces

            init_persistent_traces(os.path.join(data_dir, "traces.db"))
        except Exception as e:
            viki_logger.debug("init_persistent_traces failed: %s", e)
        self.active_tasks = []
        self.pending_actions = {}  # For confirmation flow, keyed by session
        self.pending_ops_plans = {}  # For ops approval flow, keyed by session
        self._last_response_meta_by_session = {}
        # Cumulative LLM token/cost totals per chat session (API/SSE exposure).
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
        # Phase 0: Cognitive routing — wires Reflex + Judgment into the hot path.
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

        # v26: Tenant-aware Ops planner (creates OpsPlan before any side effects)
        self.ops_planner = SimpleOpsPlanner(self)
        self.forge_orchestrator = ForgeOrchestrator(self)

        self.safe_mode = False
        self.internal_trace = []
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

        # v13: Autonomous Startup Pulse — skipped in low_resource_mode or VIKI_SKIP_STARTUP_PULSE (headless evolve).
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

        # Background Ollama pre-warm. Fires a 1-token ping at the default
        # model so by the time the user types their first real question, the
        # model weights are loaded into RAM/VRAM. Gated by the
        # `system.prewarm_default_model` flag (default true), and disabled in
        # low_resource_mode and air_gap. Failures are swallowed — boot must
        # never block on this.
        prewarm_enabled = (
            self.settings.get("system", {}).get("prewarm_default_model", True)
            and not getattr(self, "low_resource_mode", False)
            and not getattr(self, "air_gap", False)
        )
        if prewarm_enabled:
            try:
                asyncio.get_running_loop()
                self._create_tracked_task(self._prewarm_default_model(), "ollama_prewarm")
            except RuntimeError:
                viki_logger.debug("Sync Mode: Ollama prewarm deferred (no running loop).")

        # --- ORYTHIX COGNITIVE ARCHITECTURE (v22 Evolution) ---
        self.governor = EthicalGovernor()
        self.self_model = SelfModel(governor=self.governor)
        # Using self.memory.episodic for alignment
        self.narrative = self.memory.episodic
        self.deliberation = DeliberationEngine(llm=self.model_router, self_model=self.self_model)

        # Phase 6: Autonomy
        self.mission_control = MissionControl(
            request_processor=self,
            system_settings=self.settings.get("system", {}),
            signals=self.signals,
        )
        self._preflight_pipeline = build_default_preflight_pipeline()

        # Endpoint guard runs in a background thread; start here so API/sync construction
        # (no asyncio loop) still enables the watcher. Idempotent if also triggered later.
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

    def _on_config_file_changed(self, path: str) -> None:
        """Callback invoked by ConfigWatcher when a tracked YAML changes."""
        try:
            fresh = self._load_yaml(path)
            if not fresh:
                return
            if "settings.yaml" in path or path.endswith("settings.yaml"):
                self.settings.update(fresh)
                self._apply_system_overrides(self.settings.setdefault("system", {}), None)
                self._resolve_models_config(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                )
                viki_logger.info("Config hot-reload: settings.yaml applied.")
            elif "models.yaml" in path or path.endswith("models.yaml"):
                self.models_config = fresh
                if hasattr(self, "model_router") and self.model_router is not None:
                    self.model_router._load_config()
                viki_logger.info("Config hot-reload: models.yaml applied.")
        except Exception as e:
            viki_logger.warning("Config hot-reload failed for %s: %s", path, e)

    async def _startup_pulse(self):
        """Autonomous startup sequence: Connect, Research, Evolve.

        Heavy steps (research pulse, evolution pulse, workspace scan,
        mission control, continuous learning) all check
        `low_resource_mode` and short-circuit when it is on, so VIKI
        boots cleanly on machines with little RAM / IO budget.
        """
        await asyncio.sleep(5)  # Give other services time to start
        if getattr(self, "low_resource_mode", False):
            viki_logger.info(
                "STARTUP PULSE: low_resource_mode ON — skipping autonomous startup pulse."
            )
            return

        viki_logger.info("VIKIController Initialized: Sovereign Intelligence Orchestrator (v8.1.0)")
        self.telemetry.record("system", "startup", {"version": "8.1.0", "mode": "sovereign"})

        # v27: Check for active missions from WorldModel
        active_mission = self.world.get_active_mission()
        if active_mission:
            viki_logger.info(
                f"RESUME ADVISORY: Detected active mission: {active_mission['goal'][:50]}..."
            )
            viki_logger.info(f"Phase: {active_mission['phase']}. Use '/resume' to continue.")

        viki_logger.info("STARTUP PULSE: Initiating autonomous knowledge sync...")

        # 1. Quick Research Pulse (optional; disable with system.startup_research: false to speed first request)
        if not self.air_gap and self.settings.get("system", {}).get("startup_research", False):
            try:
                research_skill = self.skill_registry.get_skill("research")
                if research_skill:
                    viki_logger.info("Startup: Checking web for latest digital trends...")
                    await research_skill.execute(
                        {"query": "latest tech and ai news today", "num_results": 2}
                    )
            except Exception as e:
                viki_logger.debug(f"Startup research pulse failed: {e}")

        # 2. Check for pending evolution (defer if background boot evolution will run later)
        forge_cfg = self.settings.get("forge") or {}
        defer_boot_evolution = bool(forge_cfg.get("background_evolution_at_boot"))
        new_lessons = self.learning.get_total_lesson_count()
        if not defer_boot_evolution and new_lessons >= 5:
            viki_logger.info(
                f"Startup: {new_lessons} lessons found. Triggering neural optimization."
            )
            forge = self.skill_registry.get_skill("internal_forge")
            if forge:
                await forge.execute({"steps": 20})
        elif defer_boot_evolution:
            delay_s = max(0, int(forge_cfg.get("boot_evolution_delay_s", 180)))
            viki_logger.info(
                "Startup: background_evolution_at_boot enabled — deferring ingest+forge by %ss.",
                delay_s,
            )
            self._create_tracked_task(self._boot_evolution_after_delay(delay_s), "boot_evolution")

        # 3. Autonomous World Discovery (v22) — gated to skip on low-resource hosts.
        workspace_dir = self.settings.get("system", {}).get(
            "workspace_dir", self.DEFAULT_WORKSPACE_DIR
        )
        if os.path.exists(workspace_dir):
            viki_logger.info(f"Startup: Initiating autonomous world mapping for {workspace_dir}...")
            self.world.analyze_workspace(workspace_dir)
            self.world.scan_codebase(workspace_dir)

        # 4. Engage Mission Control
        if not self.air_gap:
            self._create_tracked_task(self.mission_control.start_loop(), "mission_control")

        # 5. Start Continuous Learning Monitor (checks periodically for training)
        self._create_tracked_task(self._continuous_learning_loop(), "continuous_learning")

    def track_touched_item(self, category: str, item: str):
        """Track a file, command, or domain for the session dashboard."""
        if category not in self.session_history:
            return
        # Redact before storing if it's a command or file with potentially sensitive name
        redacted = self.safety.sanitize_output(item)
        if redacted not in self.session_history[category]:
            self.session_history[category].insert(0, redacted)
            self.session_history[category] = self.session_history[category][:10]

    def get_sovereign_status(self) -> dict[str, Any]:
        """Returns a snapshot of the current security and boundary status."""
        workspace_dir = self.settings.get("system", {}).get(
            "workspace_dir", self.DEFAULT_WORKSPACE_DIR
        )
        data_dir = self.settings.get("system", {}).get("data_dir", self.DEFAULT_DATA_DIR)

        shell_cap = self.capabilities.get("shell_exec")
        research_cap = self.capabilities.get("internet_research")

        return {
            "filesystem": {
                "workspace": os.path.abspath(workspace_dir),
                "data": os.path.abspath(data_dir),
                "allowed_roots_count": len(self.settings.get("system", {}).get("allowed_roots", []))
                or 2,
            },
            "network": {
                "air_gap": self.air_gap,
                "local_llm_only": self.settings.get("system", {}).get("local_llm_only", False),
                "allowlist_count": len(research_cap.meta.get("destination_allowlist", []))
                if research_cap
                else 0,
            },
            "shell": {
                "enabled": shell_cap.enabled if shell_cap else False,
                "approval_required": shell_cap.requires_confirmation if shell_cap else True,
            },
            "privacy": {"redaction_active": True, "shadow_mode": self.shadow_mode},
            "history": self.session_history,
        }

    async def _boot_evolution_after_delay(self, delay_s: int) -> None:
        await asyncio.sleep(delay_s)
        try:
            msg = await self.run_boot_evolution_work(force=False)
            viki_logger.info("Boot evolution: %s", msg)
        except Exception as e:
            viki_logger.warning("Boot evolution failed: %s", e)

    async def run_boot_evolution_work(self, force: bool = False) -> str:
        """
        Background web ingest + prompt-bake forge. Grows lesson DB and Modelfile SYSTEM block;
        does not change the byte size of the base GGUF weights.

        Use force=True from headless scripts (see scripts/viki_headless_boot_evolve.py).
        """
        forge_cfg = self.settings.get("forge") or {}
        if not force and not bool(forge_cfg.get("background_evolution_at_boot")):
            return "skipped (background_evolution_at_boot false)"
        if getattr(self, "air_gap", False):
            return "skipped (air_gap)"
        if getattr(self, "low_resource_mode", False):
            return "skipped (low_resource_mode)"
        if getattr(self, "shadow_mode", False):
            return "skipped (shadow_mode)"

        research_skill = self.skill_registry.get_skill("research")
        if not research_skill:
            return "skipped (research skill not registered)"

        data_dir = self.settings.get("system", {}).get("data_dir", self.DEFAULT_DATA_DIR)
        topics: list[str] = []
        extra = forge_cfg.get("boot_research_queries") or []
        if isinstance(extra, list):
            topics.extend(str(t).strip() for t in extra if str(t).strip())
        topics_file = str(forge_cfg.get("boot_topics_file") or "boot_topics.txt").strip()
        tp = os.path.join(data_dir, topics_file)

        def _read_topics_file(path: str) -> list[str]:
            out: list[str] = []
            try:
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            out.append(line)
            except OSError as e:
                viki_logger.debug("boot_topics_file read: %s", e)
            return out

        if os.path.isfile(tp):
            topics.extend(await asyncio.to_thread(_read_topics_file, tp))

        if not topics:
            topics = [
                "recent science and technology news summary",
                "one notable AI or software release this month",
            ]

        cap = max(1, min(int(forge_cfg.get("boot_research_query_count", 3)), 10))
        lessons_before = self.learning.get_total_lesson_count()

        for q in topics[:cap]:
            try:
                viki_logger.info("Boot evolution: research query: %s", q[:80])
                await asyncio.wait_for(research_skill.execute({"query": q}), timeout=45.0)
            except TimeoutError:
                viki_logger.warning("Boot evolution: research timeout for query.")
            except Exception as e:
                viki_logger.debug("Boot evolution research: %s", e)
            await asyncio.sleep(2.0)

        lessons_after = self.learning.get_total_lesson_count()
        min_lessons = max(1, int(forge_cfg.get("boot_forge_min_lessons", 3)))
        if lessons_after < min_lessons:
            return (
                f"ingested web snippets (lessons {lessons_before}->{lessons_after}); "
                f"forge skipped (need>={min_lessons} lessons)"
            )

        forge = self.skill_registry.get_skill("internal_forge")
        if not forge:
            return "lessons updated; forge skill missing"

        steps = max(5, min(int(forge_cfg.get("boot_forge_steps", 25)), 120))
        allow_gpu = bool(forge_cfg.get("allow_auto_gpu_training_at_boot"))
        params: dict[str, Any] = {"steps": steps}
        if allow_gpu:
            params["strategy"] = "auto"
        else:
            params["strategy"] = "prompt_bake"

        viki_logger.info("Boot evolution: running internal_forge %s", params)
        result = await forge.execute(params)
        return f"forge result: {result[:500]} (lessons {lessons_before}->{self.learning.get_total_lesson_count()})"

    async def _prewarm_default_model(self):
        """
        Fire a tiny 1-token ping at the default chat model so Ollama loads it
        into memory before the user's first real prompt. Cuts ~5–15 s off
        the cold first-reply on a 4 GB / 4-core box.
        """
        try:
            await asyncio.sleep(1.5)  # let boot settle / MCP attach finish
            if not self.model_router:
                return
            try:
                model = self.model_router.get_model(["chatter"])
            except Exception as e:
                viki_logger.debug(f"Prewarm: model_router.get_model failed: {e}")
                return
            if model is None:
                return
            chat_fn = getattr(model, "chat", None)
            if chat_fn is None:
                return
            t0 = time.time()
            try:
                if asyncio.iscoroutinefunction(chat_fn):
                    try:
                        await chat_fn([{"role": "user", "content": "."}])
                    except TypeError:
                        # Some chat() signatures take temperature as positional.
                        await chat_fn([{"role": "user", "content": "."}], 0.0)
                else:
                    chat_fn([{"role": "user", "content": "."}])
            except Exception as e:
                viki_logger.debug(f"Prewarm chat failed (non-fatal): {e}")
                return
            elapsed = time.time() - t0
            viki_logger.info(
                f"Prewarm: default model '{getattr(model, 'model_name', '?')}' loaded in {elapsed:.1f}s."
            )
        except Exception as e:
            viki_logger.debug(f"Prewarm task swallowed: {e}")

    def _create_tracked_task(self, coro, name: str = "unnamed"):
        """Create a background task with proper tracking and error handling."""
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        task.add_done_callback(lambda t: self._handle_task_exception(t, name))
        viki_logger.debug(f"Created tracked background task: {name}")
        return task

    def _handle_task_exception(self, task: asyncio.Task, name: str):
        """Handle exceptions from background tasks."""
        try:
            task.result()
        except asyncio.CancelledError:
            viki_logger.debug(f"Background task '{name}' was cancelled")
        except Exception as e:
            viki_logger.error(f"Background task '{name}' failed with exception: {e}", exc_info=True)

    def check_skill_health(self) -> None:
        """Optional startup check: log warnings for degraded runtime or misconfigured integrations."""
        if not self.settings.get("system", {}).get("skill_health_check", True):
            return
        integrations = self.settings.get("integrations", {})
        health = self.get_runtime_health()
        # Gmail
        self._check_integration_credentials(
            integrations.get("gmail", {}),
            "VIKI_GMAIL_CREDENTIALS_PATH",
            "Gmail",
            "Set integrations.gmail.credentials_path or VIKI_GMAIL_CREDENTIALS_PATH",
        )
        self._check_integration_credentials(
            integrations.get("google_calendar", {}),
            "VIKI_GOOGLE_CALENDAR_CREDENTIALS_PATH",
            "Google Calendar",
            "Set integrations.google_calendar.credentials_path or VIKI_GOOGLE_CALENDAR_CREDENTIALS_PATH",
        )
        # Research (presence only)
        if not self.skill_registry.get_skill("research"):
            viki_logger.warning("Skill health: research skill not registered.")
        if health["degraded"]:
            disabled_skills = health["disabled_skills"]
            unavailable_models = health["unavailable_models"]
            summary_parts = []
            if disabled_skills:
                sample = ", ".join(
                    f"{name}: {reason}" for name, reason in list(disabled_skills.items())[:3]
                )
                summary_parts.append(f"{len(disabled_skills)} optional skills disabled ({sample})")
            if unavailable_models:
                sample = ", ".join(
                    f"{name}: {reason}" for name, reason in list(unavailable_models.items())[:3]
                )
                summary_parts.append(f"{len(unavailable_models)} models unavailable ({sample})")
            if summary_parts:
                viki_logger.warning(
                    "Runtime health: degraded mode active - " + " | ".join(summary_parts)
                )

    def get_runtime_health(self) -> dict[str, Any]:
        model_health = (
            self.model_router.get_health_snapshot()
            if self.model_router
            else {
                "default_model": None,
                "available_models": [],
                "unavailable_models": {},
            }
        )
        # Missing API keys for optional external-provider models should not degrade runtime health.
        # Otherwise, fresh local setups (no Anthropic/OpenAI keys) will always show degraded status.
        default_name = model_health.get("default_model")
        unavailable_models = dict(model_health.get("unavailable_models") or {})
        for name, reason in list(unavailable_models.items()):
            if name == default_name:
                continue
            if isinstance(reason, str):
                low = reason.lower()
                # Common APILLM init failures when keys are unset or placeholders.
                if ("api key" in low and "missing" in low) or (
                    "api key" in low and "invalid" in low
                ):
                    unavailable_models.pop(name, None)
        # Cloud profiles are intentionally out of scope when local-only or air-gapped.
        if self.model_router and (self.local_llm_only or self.air_gap):
            for name in list(unavailable_models.keys()):
                if name == default_name:
                    continue
                inst = self.model_router.models.get(name)
                if inst is not None and inst.is_cloud():
                    unavailable_models.pop(name, None)
        model_health["unavailable_models"] = unavailable_models
        registered_skills = sorted(self.skill_registry.list_skills()) if self.skill_registry else []
        disabled_skills = dict(sorted((self.disabled_skills or {}).items()))
        warnings = []
        if disabled_skills:
            warnings.append(f"{len(disabled_skills)} optional skills disabled")
        if model_health["unavailable_models"]:
            warnings.append(f"{len(model_health['unavailable_models'])} models unavailable")
        return {
            "degraded": bool(disabled_skills or model_health["unavailable_models"]),
            "registered_skill_count": len(registered_skills),
            "registered_skills": registered_skills,
            "disabled_skills": disabled_skills,
            "default_model": model_health["default_model"],
            "available_models": model_health["available_models"],
            "unavailable_models": model_health["unavailable_models"],
            "warnings": warnings,
        }

    def get_runtime_health_summary(self) -> str:
        health = self.get_runtime_health()
        if not health["degraded"]:
            return "Runtime health: full"
        parts = []
        if health["disabled_skills"]:
            parts.append(f"{len(health['disabled_skills'])} skills disabled")

        unavailable = health.get("unavailable_models") or {}
        if unavailable:
            # Surface the actual model names so the user can act on it. For
            # Ollama-style names (`qwen3.6:latest`) we suggest a concrete
            # `ollama pull` command. The list is capped at 3 to keep the
            # summary readable.
            names = list(unavailable.keys())
            shown = names[:3]
            extra = "" if len(names) <= 3 else f" (+{len(names) - 3} more)"
            joined = ", ".join(f"'{n}'" for n in shown) + extra
            count = len(names)
            label = "model" if count == 1 else "models"
            hint = ""
            try:
                first = shown[0]
                # Ollama tags are always `name:tag`. Strip the tag for the pull hint.
                if ":" in first:
                    base = first.split(":", 1)[0]
                    hint = f" Run: ollama pull {base}"
                else:
                    hint = f" Run: ollama pull {first}"
            except Exception:
                hint = ""
            parts.append(f"{count} {label} unavailable: {joined}.{hint}")

        return "Runtime health: degraded — " + " | ".join(parts)

    async def _continuous_learning_loop(self):
        """Background loop for continuous learning checks."""
        if getattr(self, "low_resource_mode", False):
            viki_logger.info("low_resource_mode: continuous_learning_loop disabled.")
            return
        forge_settings = self.settings.get("forge", {}) or {}
        warmup_s = max(0, int(forge_settings.get("continuous_learning_warmup_s", 300)))
        interval_s = max(60, int(forge_settings.get("continuous_learning_interval_s", 21600)))
        shutdown_ev = getattr(self, "_shutdown_event", None)
        await asyncio.sleep(warmup_s)
        while True:
            if shutdown_ev is not None and shutdown_ev.is_set():
                viki_logger.info("continuous_learning_loop: shutdown requested, exiting.")
                break
            try:
                await self.continuous_learner.check_and_train()
            except Exception as e:
                viki_logger.error(f"Continuous learning check failed: {e}")
            # Sleep in small increments so shutdown can be responsive
            for _ in range(interval_s):
                if shutdown_ev is not None and shutdown_ev.is_set():
                    break
                await asyncio.sleep(1)

    async def resume_mission(self, on_event=None) -> str:
        """Resumes an active mission found in the WorldModel."""
        mission = self.world.get_active_mission()
        if not mission:
            return "No active mission found to resume."

        goal = mission["goal"]
        viki_logger.info(f"Resuming mission: {goal[:50]}...")

        # Trigger the CodingWorkflowSkill directly with the resume context
        workflow = self.skill_registry.get_skill("coding_workflow")
        if not workflow:
            return "CodingWorkflowSkill not found. Cannot resume mission."

        return await workflow.execute({"action": "resume"})

    def _load_yaml(self, path: str) -> dict[str, Any]:
        return load_yaml(path)

    def _persona_from_soul_path(self, soul_path: str) -> str:
        return persona_from_soul_path(soul_path)

    def get_differentiators(self) -> list[str]:
        """Return list of differentiators from settings (what makes VIKI specific)."""
        return self.settings.get("system", {}).get(
            "differentiators",
            [
                "Local Neural Forge",
                "Orythix governance",
                "Reflex layer",
                "Air-gap capable",
            ],
        )

    def _should_checkpoint(self, skill_name: str) -> bool:
        """True if this skill modifies files or runs shell and we should create a checkpoint before executing."""
        if skill_name in ("dev_tools", "shell", "filesystem_skill"):
            return True
        return False

    def _diff_preview(self, skill_name: str, params: dict[str, Any]) -> str:
        """Short preview of the action for confirmation message (Gemini CLI-style)."""
        if skill_name == "dev_tools":
            path = params.get("path", "?")
            if params.get("content") is not None:
                content = params.get("content", "")
                n = len(content)
                first_line = content.split("\n")[0][:60] if content else ""
                return f"Target: {path} | new content: {n} chars" + (
                    f" | first line: {first_line}..." if first_line else ""
                )
            if params.get("target") is not None and params.get("replacement") is not None:
                t, r = params.get("target", ""), params.get("replacement", "")
                return f"Target: {path} | patch: replace {len(t)} chars with {len(r)} chars"
        if skill_name == "shell":
            cmd = safe_for_log(params.get("command", "?"), max_len=120)
            return f"Command: {cmd}"
        if skill_name == "filesystem_skill":
            path = safe_for_log(params.get("path", "?"))
            return f"Target: {path}"
        return ""

    # Skill execution timeout: min/max bounds and default budget multiplier
    SKILL_TIMEOUT_MAX = 120
    SKILL_TIMEOUT_MIN = 30
    SKILL_TIMEOUT_BUDGET_DEFAULT = 5
    SKILL_TIMEOUT_BUDGET_MULTIPLIER = 12

    async def _execute_skill(
        self, skill_name: str, params: dict[str, Any], budget: dict[str, Any]
    ) -> tuple:
        """
        Execute a skill with timeout and optional checkpoint. Single place for execution logic.
        Returns (result_str_or_None, error_str_or_None, latency_float).
        """
        skill = self.skill_registry.get_skill(skill_name)
        if not skill:
            return None, f"Skill '{skill_name}' not found.", 0.0

        # Circuit breaker check
        if hasattr(self.skill_registry, "is_skill_available"):
            if not self.skill_registry.is_skill_available(skill_name):
                return None, f"Skill '{skill_name}' is temporarily unavailable (circuit open).", 0.0

        if self._should_checkpoint(skill_name):
            self.history.create_checkpoint(self, skill_name, params)
        budget_time = budget.get("time") or self.SKILL_TIMEOUT_BUDGET_DEFAULT
        skill_timeout = min(
            self.SKILL_TIMEOUT_MAX,
            max(self.SKILL_TIMEOUT_MIN, budget_time * self.SKILL_TIMEOUT_BUDGET_MULTIPLIER),
        )
        start_exec = time.time()
        try:
            result = await asyncio.wait_for(skill.execute(params), timeout=skill_timeout)
            latency = time.time() - start_exec
            try:
                from viki.core.usage_log import emit_skill_execution

                emit_skill_execution(skill_name, latency, True, None)
            except Exception:
                pass
            return (str(result), None, latency)
        except TimeoutError:
            err_msg = f"Action timed out (limit {skill_timeout}s)."
            try:
                from viki.core.usage_log import emit_skill_execution

                emit_skill_execution(skill_name, time.time() - start_exec, False, err_msg)
            except Exception:
                pass
            return None, err_msg, 0.0
        except Exception as e:
            err_msg = f"Action failed: {e}"
            try:
                from viki.core.usage_log import emit_skill_execution

                emit_skill_execution(skill_name, time.time() - start_exec, False, err_msg)
            except Exception:
                pass
            return None, err_msg, 0.0

    def _get_planner_callbacks(
        self, session_id: str, budget: dict[str, Any], on_event: Any | None
    ) -> dict[str, Any]:
        """Maps TaskGraph node types to functional skill executions for the FSM pipeline."""

        async def _generic_exec(task: Any, skill: str, forced_params: dict[str, Any] | None = None):
            if on_event:
                on_event("status", f"PLANNER: {task.description}")
            params = (task.parameters if isinstance(task.parameters, dict) else {}).copy()
            if forced_params:
                params.update(forced_params)

            # Special case for shell commands: ensure 'command' is present
            if skill == "shell" and "command" not in params:
                # If the planner put the command in 'parameters' but not under 'command' key
                # though typically parameters IS the dict.
                pass

            res, err, lat = await self._execute_skill(skill, params, budget)
            if err:
                raise RuntimeError(err)
            return res

        async def _analyze(task: Any):
            if on_event:
                on_event("status", f"PLANNER ANALYZING: {task.description}")
            model = self.model_router.get_model(["reasoning", "fast_response"])
            prompt = (
                f"You are the VIKI Execution Agent.\n"
                f"Goal: {self.world.state.active_goal}\n"
                f"Current Task: {task.description}\n"
                f"Context: {task.parameters}\n\n"
                f"Provide a technical analysis or plan for this specific step."
            )
            return await model.chat([{"role": "user", "content": prompt}])

        return {
            "search_repo": lambda t: _generic_exec(t, "code_search"),
            "read_file": lambda t: _generic_exec(t, "dev_tools", {"action": "read_file"}),
            "write": lambda t: _generic_exec(t, "dev_tools", {"action": "write_file"}),
            "patch": lambda t: _generic_exec(t, "dev_tools", {"action": "patch_file"}),
            "run_tests": lambda t: _generic_exec(t, "shell"),
            "refactor": lambda t: _generic_exec(t, "dev_tools", {"action": "patch_file"}),
            "analyze": _analyze,
            "reflect": _analyze,
            "shell": lambda t: _generic_exec(t, "shell"),
            "create": lambda t: _generic_exec(t, "shell"),
        }

    def _json_type_matches(self, value: Any, expected_type: str) -> bool:
        return json_type_matches(value, expected_type)

    def _validate_required_params(self, required: list[str], params: dict[str, Any]) -> str | None:
        """Validate required schema fields are present and non-empty."""
        for field in required:
            if field not in params:
                return f"Tool contract violation: missing required param '{field}'."
            val = params.get(field)
            if val is None:
                return f"Tool contract violation: required param '{field}' is None."
            if isinstance(val, str) and not val.strip():
                return f"Tool contract violation: required param '{field}' is empty."
        return None

    def _validate_param_spec(self, field: str, spec: dict[str, Any], val: Any) -> str | None:
        """Validate enum/type constraints for a single parameter spec."""
        if "enum" in spec and isinstance(spec["enum"], list):
            allowed = spec["enum"]
            if val not in allowed:
                return f"Tool contract violation: param '{field}' must be one of {allowed}, got {val!r}."

        expected_type = spec.get("type")
        if expected_type and not self._json_type_matches(val, str(expected_type)):
            return f"Tool contract violation: param '{field}' expected type '{expected_type}', got {type(val).__name__}."

        return None

    def _validate_property_constraints(
        self, props: dict[str, Any], params: dict[str, Any]
    ) -> str | None:
        """Validate provided parameters against enum/type constraints in schema."""
        for field, spec in props.items():
            if field not in params or not isinstance(spec, dict):
                continue
            val = params.get(field)
            err = self._validate_param_spec(field, spec, val)
            if err:
                return err
        return None

    def _validate_tool_contract_params(self, skill_name: str, params: dict[str, Any]) -> str | None:
        """
        Validate incoming params against the skill's declared `schema`.
        Returns None if validation passes, otherwise a tool-contract error string.
        """
        skill = self.skill_registry.get_skill(skill_name)
        if not skill:
            return f"Tool contract violation: skill '{skill_name}' not found."

        schema = getattr(skill, "schema", None) or {}
        if not isinstance(schema, dict) or not schema:
            # No contract available; don't block.
            return None

        required = schema.get("required") or []
        props = schema.get("properties") or {}
        err = self._validate_required_params(required, params)
        if err:
            return err
        return self._validate_property_constraints(props, params)

    def _validate_skill_output(self, skill_name: str, output: Any) -> str | None:
        """
        Validate skill output for common failure modes (empty output, explicit errors, or safety-contradictions).
        Returns None if valid, otherwise a tool-contract output validation error string.
        """
        if output is None:
            return f"Tool contract output validation failed: '{skill_name}' returned None."

        out_str = output if isinstance(output, str) else str(output)
        if not out_str.strip():
            return (
                f"Tool contract output validation failed: '{skill_name}' returned an empty string."
            )

        out_lower = out_str.strip().lower()
        error_signals = ("error:", "command failed", "shell error:", "action failed:")
        if any(s in out_lower for s in error_signals):
            return f"Tool contract output validation failed: '{skill_name}' produced an error-like result."

        # Reuse existing safety response validators for hallucination patterns.
        try:
            resp_check = self.safety.validate_response(out_str)
            if not resp_check.get("valid", True):
                issues = resp_check.get("issues") or []
                return f"Tool contract output validation failed: '{skill_name}' output failed safety validation: {issues}"
        except Exception:
            # If validation itself fails, don't block execution completion.
            pass

        return None

    def _should_plan_ops(self, text: str) -> bool:
        """
        Heuristic detector for first tenant ops path: scheduling/cancellation.
        Kept conservative to avoid triggering on generic "event loop" text.
        """
        t = (text or "").lower()
        has_schedule_intent = any(k in t for k in ("schedule", "appointment", "meeting", "event"))
        has_time_hint = any(k in t for k in ("tomorrow", "today", "at ")) or bool(
            re.search(r"\d{1,2}(:\d{2})?\s*(am|pm)", t)
        )
        has_cancel_intent = any(
            k in t for k in ("cancel", "cancellation", "remove", "delete")
        ) and any(k in t for k in ("meeting", "appointment", "event"))
        return (has_schedule_intent and has_time_hint) or has_cancel_intent

    async def _apply_ops_plan(self, plan: OpsPlan, session_id: str) -> str:
        """
        Execute a previously-approved OpsPlan via controller skills (calendar + messaging).
        """
        if self.shadow_mode:
            return (
                f"[Shadow Mode] Would apply OpsPlan: {plan.update_type} ({plan.proposed_changes})."
            )

        connector = ControllerTenantConnector(self, tenant_id=plan.tenant_id)

        changes = dict(plan.proposed_changes or {})
        changes["update_type"] = plan.update_type
        apply_res = await connector.apply_changes(changes)
        if not apply_res.get("ok", False):
            return f"Ops execution failed: {apply_res.get('error', 'unknown error')}"

        send_res = await connector.send_messages(plan.message_drafts or [])

        # Human-readable summary.
        cal_res = (
            (apply_res.get("calendar") or {}).get("result")
            if isinstance(apply_res.get("calendar"), dict)
            else None
        )
        msg_results = send_res.get("results", []) if isinstance(send_res, dict) else []
        msg_summary = "; ".join(
            f"{r.get('channel')}={r.get('result') or r.get('error')}"
            for r in msg_results
            if isinstance(r, dict)
        )

        # Clear pending state after execution.
        self.pending_ops_plans.pop(session_id, None)

        return (
            f"OpsPlan applied: {plan.update_type}.\n"
            f"Calendar: {cal_res or 'n/a'}\n"
            f"Messages: {msg_summary or 'n/a'}"
        )

    # Heavy skills that import optional/expensive deps (torch, playwright,
    # pandas, pdfplumber, onnxruntime, whisper, transformers, etc.). These are
    # registered as LazySkillProxy on every boot — they only fully load when
    # the planner actually invokes them. Reduces cold-start by ~30–60% on
    # low-end Windows boxes.
    _LAZY_SKILL_SPECS = [
        # (skill_name, description, module_path, class_name, needs_controller, safety_tier)
        (
            "look_at_screen",
            "Capture and describe screen content.",
            "skills.builtins.vision_skill",
            "VisionSkill",
            False,
            "safe",
        ),
        (
            "python_interpreter",
            "Execute Python in a sandbox.",
            "skills.builtins.interpreter_skill",
            "InterpreterSkill",
            True,
            "medium",
        ),
        (
            "browser",
            "Headless browser navigation and scraping.",
            "skills.builtins.browser_skill",
            "BrowserSkill",
            False,
            "medium",
        ),
        (
            "swarm_control",
            "Multi-agent swarm orchestration.",
            "skills.builtins.swarm_skill",
            "SwarmSkill",
            True,
            "medium",
        ),
        (
            "draw_overlay",
            "Floating overlay UI.",
            "skills.builtins.overlay_skill",
            "OverlaySkill",
            False,
            "safe",
        ),
        (
            "short_video_agent",
            "Generate short videos.",
            "skills.builtins.short_video_skill",
            "ShortVideoSkill",
            True,
            "safe",
        ),
        (
            "calendar",
            "Google Calendar integration.",
            "skills.builtins.calendar_skill",
            "CalendarSkill",
            True,
            "safe",
        ),
        ("email", "Gmail integration.", "skills.builtins.email_skill", "EmailSkill", True, "safe"),
        (
            "messaging",
            "Unified messaging across Discord/Telegram/etc.",
            "skills.builtins.messaging_skill",
            "UnifiedMessagingSkill",
            True,
            "safe",
        ),
        (
            "twitter",
            "Twitter/X integration.",
            "skills.builtins.twitter_skill",
            "TwitterSkill",
            False,
            "safe",
        ),
        (
            "summarize",
            "Summarize long text/web pages.",
            "skills.builtins.summarize_skill",
            "SummarizeSkill",
            True,
            "safe",
        ),
        (
            "image_gen",
            "Generate images.",
            "skills.builtins.image_gen_skill",
            "ImageGenSkill",
            False,
            "safe",
        ),
        (
            "obsidian",
            "Obsidian vault notes.",
            "skills.builtins.obsidian_skill",
            "ObsidianSkill",
            True,
            "safe",
        ),
        (
            "tasks",
            "Task list management.",
            "skills.builtins.tasks_skill",
            "TasksSkill",
            True,
            "safe",
        ),
        (
            "whisper",
            "Audio transcription.",
            "skills.builtins.whisper_skill",
            "WhisperSkill",
            True,
            "safe",
        ),
        (
            "pdf",
            "PDF reading and extraction.",
            "skills.builtins.pdf_skill",
            "PdfSkill",
            True,
            "safe",
        ),
        (
            "smart_home",
            "Smart-home device control.",
            "skills.builtins.smart_home_skill",
            "SmartHomeSkill",
            False,
            "medium",
        ),
        ("gif", "GIF generation.", "skills.builtins.gif_skill", "GifSkill", False, "safe"),
        (
            "data_analysis",
            "DataFrame analysis.",
            "skills.builtins.data_analysis_skill",
            "DataAnalysisSkill",
            True,
            "safe",
        ),
        (
            "presentation",
            "Slide deck generation.",
            "skills.builtins.presentation_skill",
            "PresentationSkill",
            True,
            "safe",
        ),
        (
            "spreadsheet",
            "Spreadsheet generation/editing.",
            "skills.builtins.spreadsheet_skill",
            "SpreadsheetSkill",
            True,
            "safe",
        ),
        (
            "website",
            "Website scaffolding/editing.",
            "skills.builtins.website_skill",
            "WebsiteSkill",
            True,
            "safe",
        ),
        (
            "code_search",
            "Repository code search.",
            "skills.builtins.code_search_skill",
            "CodeSearchSkill",
            True,
            "safe",
        ),
        (
            "plan_edit",
            "Multi-file plan-edit-verify loop.",
            "skills.builtins.plan_edit_skill",
            "PlanEditSkill",
            True,
            "medium",
        ),
        (
            "computer_use",
            "Vision-grounded UI automation.",
            "skills.builtins.computer_use_skill",
            "ComputerUseSkill",
            True,
            "medium",
        ),
    ]

    def _register_default_skills(self):
        from skills.lazy_skill import LazySkillProxy

        allowlist = self.soul.config.get("skill_allowlist")
        low_resource = bool(
            (self.settings.get("system") or {}).get("low_resource_mode")
            or os.environ.get("VIKI_LOW_RESOURCE", "").lower() in ("1", "true", "yes")
        )

        def _load_skill(module_path: str, class_name: str, *args):
            try:
                module = importlib.import_module(module_path)
                cls = getattr(module, class_name, None)
                if not cls:
                    # Case-insensitive fallback
                    for attr in dir(module):
                        if attr.lower() == class_name.lower():
                            cls = getattr(module, attr)
                            break
                if not cls:
                    return None

                # Check constructor signature or just try-catch
                try:
                    return cls(*args)
                except TypeError:
                    # Fallback for skills that don't accept controller yet
                    return cls()
            except Exception as e:
                viki_logger.warning(f"Skill '{class_name}' from {module_path} disabled: {e}")
                self.disabled_skills[class_name] = str(e)
                return None

        # Eager skills: cheap to import and used on the hot path.
        eager_specs = [
            ("skills.builtins.time_skill", "TimeSkill", ()),
            ("skills.builtins.math_skill", "MathSkill", ()),
            ("skills.builtins.filesystem_skill", "FileSystemSkill", (self,)),
            ("skills.thinking", "ThinkingSkill", ()),
            ("skills.builtins.system_control_skill", "SystemControlSkill", ()),
            ("skills.builtins.research_skill", "ResearchSkill", (self,)),
            ("skills.builtins.dev_skill", "DevSkill", (self,)),
            ("skills.builtins.voice_skill", "VoiceSkill", (self.voice_module, self)),
            ("skills.builtins.sfs_skill", "SemanticFSSkill", (self,)),
            ("skills.builtins.security_skill", "SecuritySkill", ()),
            ("skills.builtins.endpoint_guard_skill", "EndpointGuardSkill", (self,)),
            ("skills.creation.forge", "ModelForgeSkill", (self,)),
            ("skills.builtins.recall_skill", "RecallSkill", (self,)),
            ("skills.builtins.memory_skill", "MemorySkill", (self,)),
            ("skills.builtins.media_skill", "MediaControlSkill", ()),
            ("skills.builtins.clipboard_skill", "ClipboardSkill", ()),
            ("skills.builtins.window_management_skill", "WindowManagerSkill", ()),
            ("skills.builtins.shell_skill", "ShellSkill", (self,)),
            ("skills.builtins.notification_skill", "NotificationSkill", ()),
            ("skills.builtins.coding_workflow_skill", "CodingWorkflowSkill", (self,)),
            ("skills.builtins.lsp_skill", "LspSkill", (self,)),
        ]
        # v27: Dynamic Skill Discovery for Builtins
        import pkgutil

        import skills.builtins as builtins_pkg

        discovered_specs = []
        registered_modules = {s[0] for s in eager_specs} | {s[2] for s in self._LAZY_SKILL_SPECS}

        for _, modname, ispkg in pkgutil.iter_modules(builtins_pkg.__path__):
            if ispkg:
                continue
            full_modname = f"skills.builtins.{modname}"
            if full_modname in registered_modules:
                continue

            # Skip known helpers or non-skill modules
            if modname in ("code_index_watcher", "legacy_math"):
                continue

            # Simple heuristic: CamelCase class name from snake_case module
            class_name = "".join(word.capitalize() for word in modname.split("_"))
            if not class_name.endswith("Skill") and class_name not in ("LSPSkill", "SFS"):
                # Avoid double "Skill" but ensure it's there for most
                class_name += "Skill"

            discovered_specs.append((full_modname, class_name, (self,)))
            viki_logger.debug(f"Discovered skill: {class_name} in {full_modname}")

        all_skills = []
        for module_path, class_name, args in eager_specs + discovered_specs:
            skill = _load_skill(module_path, class_name, *args)
            if skill is not None:
                all_skills.append(skill)

        # Lazy heavy skills: register a proxy so they appear in the registry
        # but only import when first invoked.
        for spec in self._LAZY_SKILL_SPECS:
            sname, sdesc, smod, scls, needs_ctrl, stier = spec

            def _ctor(ctrl, scls=scls, needs_ctrl=needs_ctrl):
                if scls == "SwarmSkill":
                    return (ctrl.swarm, ctrl)
                return (ctrl,) if needs_ctrl else ()

            try:
                proxy = LazySkillProxy(
                    name=sname,
                    description=sdesc,
                    module_path=smod,
                    class_name=scls,
                    ctor_args=_ctor,
                    controller=self,
                    safety_tier=stier,
                )
                all_skills.append(proxy)
            except Exception as e:
                viki_logger.warning(f"LazySkillProxy '{sname}' failed: {e}")
                self.disabled_skills[scls] = str(e)

        # Low-resource mode: also lazify dev/research/voice etc. is overkill;
        # we only drop strictly optional eager skills that would never get
        # used unless the user asks. Currently the eager set is already lean,
        # so the flag mainly affects proactive loops downstream. Surface a
        # log line so operators know the mode is active.
        if low_resource:
            viki_logger.info(
                "VIKIController: low_resource_mode is ON — proactive loops "
                "(wellness, dream, continuous-learning, startup pulse) will be skipped."
            )
            self.low_resource_mode = True
        else:
            self.low_resource_mode = False

        allowed = set(allowlist) if allowlist else None
        for skill in all_skills:
            if allowed is None or skill.name in allowed:
                self.skill_registry.register_skill(skill)

        # v26: Load Sovereign Tool Hub (100+ Skills)
        library_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "sovereign_library.json",
        )
        self.skill_registry.load_sovereign_library(library_path, self)

        # Aliases: only add if target skill is registered
        self._apply_skill_aliases()

    def _normalize_session_id(self, session_id: str | None = None) -> str:
        return session_id or getattr(self.memory.working, "default_session_id", "default")

    def get_last_response_meta(self, session_id: str | None = None) -> dict[str, Any]:
        session_id = self._normalize_session_id(session_id)
        meta = dict(self._last_response_meta_by_session.get(session_id, {}))
        usage = self._session_llm_usage.get(session_id)
        if usage:
            meta["usage"] = {
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "total_cost_usd": round(float(usage.get("total_cost_usd", 0.0)), 6),
                "by_model": dict(usage.get("by_model") or {}),
            }
        return meta

    def get_session_usage(self, session_id: str | None = None) -> dict[str, Any]:
        """Rolling LLM usage for this session (tokens + estimated USD)."""
        session_id = self._normalize_session_id(session_id)
        u = self._session_llm_usage.get(session_id)
        if not u:
            return {
                "session_id": session_id,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_cost_usd": 0.0,
                "by_model": {},
            }
        return {
            "session_id": session_id,
            "input_tokens": int(u.get("input_tokens", 0)),
            "output_tokens": int(u.get("output_tokens", 0)),
            "total_cost_usd": round(float(u.get("total_cost_usd", 0.0)), 6),
            "by_model": dict(u.get("by_model") or {}),
        }

    def reset_session_usage(self, session_id: str | None = None) -> None:
        session_id = self._normalize_session_id(session_id)
        self._session_llm_usage.pop(session_id, None)

    def _router_usage_snapshot(self) -> dict[str, tuple[int, int, float]]:
        snap: dict[str, tuple[int, int, float]] = {}
        try:
            for name, model in (self.model_router.models or {}).items():
                snap[name] = (
                    int(getattr(model, "input_tokens", 0) or 0),
                    int(getattr(model, "output_tokens", 0) or 0),
                    float(getattr(model, "total_cost_usd", 0.0) or 0.0),
                )
        except Exception as e:
            viki_logger.debug("_router_usage_snapshot: %s", e)
        return snap

    def _accumulate_session_usage_from_delta(
        self,
        session_id: str,
        baseline: dict[str, tuple[int, int, float]],
    ) -> None:
        sid = self._normalize_session_id(session_id)
        bucket = self._session_llm_usage.setdefault(
            sid,
            {"input_tokens": 0, "output_tokens": 0, "total_cost_usd": 0.0, "by_model": {}},
        )
        by_model: dict[str, Any] = bucket.setdefault("by_model", {})
        try:
            for name, model in (self.model_router.models or {}).items():
                cur = (
                    int(getattr(model, "input_tokens", 0) or 0),
                    int(getattr(model, "output_tokens", 0) or 0),
                    float(getattr(model, "total_cost_usd", 0.0) or 0.0),
                )
                b = baseline.get(name, (0, 0, 0.0))
                di, dout, dc = cur[0] - b[0], cur[1] - b[1], cur[2] - b[2]
                if di or dout or dc:
                    bucket["input_tokens"] = int(bucket.get("input_tokens", 0)) + di
                    bucket["output_tokens"] = int(bucket.get("output_tokens", 0)) + dout
                    bucket["total_cost_usd"] = float(bucket.get("total_cost_usd", 0.0)) + dc
                    bm = by_model.setdefault(
                        name,
                        {"input_tokens": 0, "output_tokens": 0, "total_cost_usd": 0.0},
                    )
                    bm["input_tokens"] = int(bm.get("input_tokens", 0)) + di
                    bm["output_tokens"] = int(bm.get("output_tokens", 0)) + dout
                    bm["total_cost_usd"] = float(bm.get("total_cost_usd", 0.0)) + dc
        except Exception as e:
            viki_logger.debug("_accumulate_session_usage_from_delta: %s", e)

    def _skill_action_severity(self, skill_name: str, params: dict[str, Any]) -> str:
        skill_obj = self.skill_registry.get_skill(skill_name) if self.skill_registry else None
        if skill_obj is not None and skill_name.startswith("mcp_"):
            st = (getattr(skill_obj, "safety_tier", None) or "medium").lower()
            if st == "destructive":
                return "destructive"
            if st == "medium":
                return "medium"
            if getattr(skill_obj, "requires_user_confirmation", False):
                return "medium"
            return "safe"
        return self.safety.get_action_severity(skill_name, params)

    def get_router_telemetry(self) -> dict[str, Any]:
        """Return cognitive routing telemetry (reflex hit rate, per-outcome counts)."""
        try:
            return self.router_telemetry.snapshot()
        except Exception as e:
            viki_logger.debug("get_router_telemetry: %s", e)
            return {"error": str(e)}

    async def _process_reflex_outcome(
        self, cognitive_route, safe_input, session_id, on_event=None
    ) -> str:
        """Handles immediate execution of a reflex-triggered action."""
        reflex_action_override = cognitive_route.action_override
        if reflex_action_override is None:
            return "Reflex logic error: no action provided."

        skill_name = reflex_action_override.skill_name
        params = (reflex_action_override.parameters or {}).copy()
        budget = self.budgets.get("general", self.budgets["general"])

        # Safety & Permission checks
        check_res = self.capabilities.check_permission(skill_name, params=params)
        if not check_res.allowed:
            viki_logger.warning(f"Reflex blocked: {check_res.reason}")
            return f"Reflex blocked: {check_res.reason}"

        if not self.safety.validate_action(skill_name, params):
            viki_logger.warning("Reflex blocked: safety policy.")
            return "Reflex blocked: safety policy."

        if on_event:
            on_event("status", f"REFLEX EXECUTING {skill_name}")

        result, err, latency = await self._execute_skill(skill_name, params, budget)
        if err:
            try:
                self.reflex.report_failure(safe_input)
            except Exception as e:
                viki_logger.debug(f"Reflex failure reporting failed: {e}")
            return f"Reflex execution failed: {err}"

        self.skill_registry.record_execution(skill_name, True, latency)
        msg = self._compress_output(f"Done. {result}")
        self.memory.working.add_message("assistant", msg, session_id=session_id)

        # Meta decoration for telemetry
        self._last_response_meta_by_session[session_id] = {
            "cognitive_route": cognitive_route.as_dict(),
            "reflex_executed": True,
            "latency": latency,
        }

        return msg

    async def process_request(
        self,
        user_input: str,
        on_event=None,
        on_think=None,
        attachment_paths: list[str] | None = None,
        session_id: str | None = None,
    ) -> str:
        norm_session = self._normalize_session_id(session_id)
        baseline = self._router_usage_snapshot()
        try:
            result = await self._process_request_impl(
                user_input,
                on_event=on_event,
                on_think=on_think,
                attachment_paths=attachment_paths,
                session_id=norm_session,
            )
        finally:
            self._accumulate_session_usage_from_delta(norm_session, baseline)

        # Output secret scanning
        if result:
            from viki.core.security_guard import redact_secrets

            return redact_secrets(result)
        return result or ""

    async def _process_request_impl(  # NOSONAR
        self,
        user_input: str,
        on_event=None,
        on_think=None,
        attachment_paths: list[str] | None = None,
        session_id: str | None = None,
    ) -> str:
        session_id = self._normalize_session_id(session_id)
        self._last_response_meta_by_session[session_id] = {}

        # Normalize input for robustness
        if user_input is None:
            user_input = ""
        if not isinstance(user_input, str):
            user_input = str(user_input).strip() or ""

        # Pydantic input validation
        try:
            from viki.core.input_validator import validate_user_input

            validated = validate_user_input(user_input)
            if validated is not None:
                user_input = validated
        except ImportError:
            pass

        pre_ctx = RequestContext(
            user_input=user_input,
            session_id=session_id,
            on_event=on_event,
            attachment_paths=attachment_paths,
        )
        preflight_response = await self._preflight_pipeline.run_preflight(self, pre_ctx)
        if preflight_response is not None:
            return preflight_response

        user_input = pre_ctx.user_input
        safe_input = pre_ctx.safe_input
        narrative_wisdom = pre_ctx.narrative_wisdom

        # v25: Active Context Tracking (Phase 4)
        file_matches = re.findall(r"[\w\-\.\/]+\.(?:py|js|ts|css|html|yaml|md)", user_input)
        for match in file_matches:
            if os.path.sep in match or "." in match:
                self.world.set_active_file(match)

        # 0. Fast Perception Layer (Reflex Brain)
        reflex_resp, reflex_action = self.reflex.think(user_input)
        if reflex_resp is not None:
            # Short-circuit with canned response (greetings, acknowledgments, singularity)
            viki_logger.info("Reflex hit (conversational). Returning immediately.")
            # v26.2: Sovereign Singularity Activation
            if "singularity" in reflex_resp.lower() and "activated" in reflex_resp.lower():
                self.is_singularity_mode = True
                viki_logger.info("SINGULARITY ACTIVATED via Reflex.")
            return reflex_resp

        if reflex_action is not None:
            # Short-circuit with direct action execution (time_skill, math_skill)
            viki_logger.info(
                f"Reflex hit (action: {reflex_action.skill_name}). Bypassing deliberation."
            )
            # Inject the reflex action as a pseudo-route for the rest of the pipeline
            from viki.core.cognitive_loop import CognitiveRoute, JudgmentOutcome, JudgmentResult

            reflex_route = CognitiveRoute(
                outcome=JudgmentOutcome.REFLEX,
                judgment=JudgmentResult(
                    outcome=JudgmentOutcome.REFLEX,
                    recommendation="proceed",
                    reason="Reflex hit (bypass deliberation)",
                    risk=0.0,
                    clarity=1.0,
                    novelty=0.0,
                    complexity_score=0.1,
                ),
                model_tier="fast",
                action_override=reflex_action,
                use_lite_schema=True,
                source="reflex",
            )
            return await self._process_reflex_outcome(reflex_route, safe_input, session_id)

        # Tenant Ops: OpsPlan first (no side effects until approval).
        if self._should_plan_ops(safe_input):
            tenant_id = self.settings.get("system", {}).get("tenant_id", "default")
            ops_plan = await self.ops_planner.plan(tenant_id, safe_input)

            if ops_plan.approval and ops_plan.approval.required:
                self.pending_ops_plans[session_id] = ops_plan
                what = ", ".join(ops_plan.approval.what_to_approve or [])
                return (
                    "OpsPlan created (approval gate active).\n"
                    f"Update type: {ops_plan.update_type}\n"
                    f"Proposed changes: {ops_plan.proposed_changes}\n"
                    f"ApprovalRequirement: require approval for {what or 'side effects'}.\n"
                    "Confirm with yes/confirm or cancel with no/reject."
                )

            return await self._apply_ops_plan(ops_plan, session_id=session_id)

        # Determine Task Type & Budget
        task_type = self._classify_task(safe_input)
        budget = self.budgets.get(task_type, self.budgets["general"])

        # Record user message in conversation memory (Working Trace)
        self.memory.working.add_message("user", safe_input, session_id=session_id)

        # URL Detection: If user shares a URL, auto-fetch content (with timeout)
        import re as _re

        urls = _re.findall(r'https?://[^\s<>"]+', safe_input)
        url_context = ""
        if urls:
            try:
                research_skill = self.skill_registry.get_skill("research")
                if research_skill:
                    # Cap total URL fetch time so slow pages don't block the agent
                    url_content = await asyncio.wait_for(
                        asyncio.gather(
                            *[research_skill.execute({"url": u}) for u in urls[:2]],
                            return_exceptions=True,
                        ),
                        timeout=35.0,
                    )
                    for i, res in enumerate(url_content):
                        if isinstance(res, str) and res:
                            url_context += f"\n{res}\n"
                        elif isinstance(res, Exception):
                            viki_logger.debug(
                                f"URL fetch failed for {urls[i] if i < len(urls) else '?'}: {res}"
                            )
            except TimeoutError:
                viki_logger.warning("URL fetch timed out (35s); continuing without page content.")
            except Exception as e:
                viki_logger.warning(f"URL fetch failed: {e}")

        # v26: Agent Mode (Autonomous)
        self.is_agent_mode = user_input.strip().lower().startswith("/agent")
        if self.is_agent_mode:
            viki_logger.info("AGENT MODE ACTIVATED: Engaging autonomous engineering loop.")
            # Strip the command prefix
            user_input = re.sub(r"^/agent\s*", "", user_input, flags=re.IGNORECASE).strip()
            if not user_input:
                return "Agent Mode activated. Please provide a task (e.g., /agent implement feature X)."
            safe_input = self.safety.validate_request(user_input)

        # v26: Plan Mode (Architecture & Strategy)
        self.is_plan_mode = user_input.strip().lower().startswith("/plan")
        if self.is_plan_mode:
            viki_logger.info("PLAN MODE ACTIVATED: Engaging senior architect loop.")
            # Strip the command prefix
            user_input = re.sub(r"^/plan\s*", "", user_input, flags=re.IGNORECASE).strip()
            if not user_input:
                return "Plan Mode activated. Please provide a request for architectural analysis or implementation strategy."
            safe_input = self.safety.validate_request(user_input)

        # v26: Debug Mode (Root Cause & Repair)
        self.is_debug_mode = user_input.strip().lower().startswith("/debug")
        if self.is_debug_mode:
            viki_logger.info("DEBUG MODE ACTIVATED: Engaging diagnostic loop.")
            # Strip the command prefix
            user_input = re.sub(r"^/debug\s*", "", user_input, flags=re.IGNORECASE).strip()
            if not user_input:
                return "Debug Mode activated. Please provide an error message, log, or issue description to diagnose."
            safe_input = self.safety.validate_request(user_input)

        # v19: Research vs Production Mode
        is_research = "/research" in user_input
        if is_research:
            viki_logger.info("Entering Research Mode: Exploratory & Verbose.")
            budget["time"] *= 2  # Double time for research

        if user_input.strip().lower().startswith("/benchmark"):
            return await command_handlers.handle_benchmark_command(self, user_input)

        if "/scorecard" in user_input:
            return await command_handlers.handle_scorecard_command(self)

        if "/model" in user_input:
            return await command_handlers.handle_model_command(self)

        if "/evolve" in user_input:
            return await command_handlers.handle_evolve_command(self)

        if user_input.startswith("/approve"):
            return await command_handlers.handle_approve_command(self, user_input)

        if user_input.startswith(self.REJECT_TOKEN):
            return await command_handlers.handle_reject_command(self, user_input)

        if "/crystallize" in user_input:
            return await command_handlers.handle_crystallize_command(self)

        if user_input.startswith("/forge"):
            return await command_handlers.handle_forge_command(self, user_input, session_id)

        if "/dream" in user_input:
            return await command_handlers.handle_dream_command(self)

        if "/scan" in user_input:
            return await command_handlers.handle_scan_command(self)

        if user_input.strip().lower().startswith("/restore"):
            return await command_handlers.handle_restore_command(self, user_input)

        if user_input.strip().lower() in ("/undo", "/undo last"):
            return await command_handlers.handle_undo_command(self)

        if user_input.strip().lower().startswith("/save"):
            return await command_handlers.handle_save_command(self, user_input, session_id)

        if user_input.strip().lower().startswith("/load"):
            return await command_handlers.handle_load_command(self, user_input, session_id)

        # --- ORYTHIX DELIBERATION (v22) ---
        if on_event:
            on_event("status", "DELIBERATING")

        # v23: Integrated Hierarchical Context Retrieval
        # Pass pre-fetched narrative_wisdom to avoid duplicate query
        memory_context = self.memory.get_full_context(
            safe_input, narrative_wisdom=narrative_wisdom, session_id=session_id
        )

        # Project context file (VIKI.md / VIKI_CONTEXT.md) — Gemini CLI-style
        workspace_dir = self.settings.get("system", {}).get(
            "workspace_dir", self.DEFAULT_WORKSPACE_DIR
        )
        project_instructions = ""
        for name in ("VIKI.md", "VIKI_CONTEXT.md"):
            p = os.path.join(workspace_dir, name)
            if os.path.isfile(p):
                try:
                    # v26: Context Pruning
                    # General tasks don't need the full 32KB of project context.
                    trunc_limit = 32768
                    if task_type == "general" and not (
                        self.is_agent_mode or self.is_plan_mode or self.is_debug_mode
                    ):
                        trunc_limit = 4096
                        # Pull relevant snippets via RAG if we are pruning.
                        rag_context = await self.context_retriever.get_relevant_context(safe_input)
                        if rag_context:
                            project_instructions = (project_instructions or "") + rag_context

                    project_instructions_raw = await asyncio.to_thread(
                        self._read_text_truncated, p, trunc_limit
                    )
                    project_instructions = (project_instructions or "") + project_instructions_raw
                    break
                except Exception as e:
                    viki_logger.debug(f"Could not read {p}: {e}")
        memory_context["project_instructions"] = project_instructions

        if self.settings.get("system", {}).get("git_workspace_context"):
            try:
                snap = await asyncio.to_thread(get_git_workspace_snapshot, workspace_dir)
                if snap:
                    base = memory_context.get("project_instructions") or ""
                    memory_context["project_instructions"] = (
                        (base + "\n\n" + snap).strip() if base else snap
                    )
            except Exception as e:
                viki_logger.debug("git_workspace_context: %s", e)

        # Add relevant failures to context for error avoidance
        relevant_failures = self.learning.get_relevant_failures(safe_input, limit=3)
        memory_context["relevant_failures"] = relevant_failures

        # --- SOVEREIGN GATING: Skip escalation for standard coding tasks ---
        if task_type == "coding" and not self.is_plan_mode:
            memory_context["skip_escalation"] = True

        world_understanding = self.world.get_understanding()

        # 3. Intelligence Governance (Judgment & Budget) — Phase 0: real cognitive routing.
        task_type = self._classify_task(safe_input)  # vision, coding, reasoning, general
        try:
            cognitive_route: CognitiveRoute = await self.cognitive_router.classify(
                safe_input,
                context={
                    "task_type": "question"
                    if task_type == "reasoning" and safe_input.strip().endswith("?")
                    else task_type,
                    "is_protected_zone": False,
                    "url_context_present": bool(url_context),
                },
                skill_registry=self.skill_registry,
                history=self.memory.working.get_trace(session_id=session_id),
            )
        except Exception as e:
            viki_logger.warning("Cognitive routing failed (%s); defaulting to DEEP.", e)
            cognitive_route = None

        if cognitive_route is not None:
            outcome = cognitive_route.outcome
            # Honor router decision for schema lite vs full, but allow task_type
            # to override for simple queries that don't need full schema.
            # "general" = simple chat, "reasoning" = questions that can be answered directly
            use_lite = cognitive_route.use_lite_schema or task_type in ("general", "reasoning")
        else:
            outcome = JudgmentOutcome.DEEP
            use_lite = task_type in ("general", "reasoning")

        # Short-circuit: REFUSE outcome.
        if cognitive_route is not None and cognitive_route.refusal_reason:
            self._last_response_meta_by_session[session_id] = {
                "cognitive_route": cognitive_route.as_dict(),
            }
            self.memory.working.add_message(
                "assistant",
                f"I cannot proceed with this request. {cognitive_route.refusal_reason}",
                session_id=session_id,
            )
            return f"I cannot proceed with this request. {cognitive_route.refusal_reason}"

        # Short-circuit: REFLEX cached response (no skill execution needed).
        if cognitive_route is not None and cognitive_route.cached_response:
            self._last_response_meta_by_session[session_id] = {
                "cognitive_route": cognitive_route.as_dict(),
            }
            self.memory.working.add_message(
                "assistant", cognitive_route.cached_response, session_id=session_id
            )
            return cognitive_route.cached_response

        # Behavior Modulation from Signals
        mods = self.signals.get_modulation()
        signals_state = f"Verbosity: {mods.get('verbosity', 'standard')}, Planning: {mods.get('planning_depth', 'adaptive')}, Safety: {mods.get('safety_bias', 'standard')}"
        viki_logger.debug(f"Behavior Modulation: {mods} | Outcome: {outcome.name}")

        # v25: Adaptive Agency Weightings
        agency_weights = self.evolution.get_agent_weightings()

        # --- SOVEREIGN FSM: Momentum-Based Orchestration ---
        lower_input = safe_input.lower().strip()
        from viki.core.agent_constants import MAX_PLANNING_CYCLES, SAFE_FOLLOWUP_MESSAGES

        is_continuation = lower_input in SAFE_FOLLOWUP_MESSAGES or (
            len(lower_input.split()) <= 4 and any(k in lower_input for k in SAFE_FOLLOWUP_MESSAGES)
        )

        task_type = self._classify_task(safe_input)

        # 1. Follow-up Inheritance (Sovereign Boost)
        if is_continuation and self.world.state.active_goal:
            viki_logger.info(
                f"FSM: Continuation Intent Detected. Resuming goal: {self.world.state.active_goal[:50]}..."
            )
            # Inherit last phase or force EXECUTING if we were already implementation-focused
            if self.world.state.current_phase in ("EXECUTING", "TESTING", "DEBUGGING"):
                viki_logger.debug(
                    f"FSM: Maintaining execution state: {self.world.state.current_phase}"
                )
            else:
                self.world.state.current_phase = "EXECUTING"
                self.world.state.execution_started = True

            # Sovereign Boost: Bypass cognitive routing for continuations
            if cognitive_route:
                cognitive_route.outcome = JudgmentOutcome.SHALLOW
                cognitive_route.use_lite_schema = True

        # 2. Execution Routing & Anti-Loop
        elif task_type == "coding":
            # New goal detection
            if self.world.state.active_goal != safe_input and len(safe_input) > 10:
                viki_logger.info(f"FSM: New Coding Goal: {safe_input[:50]}...")
                self.world.state.active_goal = safe_input
                self.world.state.planning_depth = 0
                self.world.state.retry_count = 0
                self.world.state.execution_started = False

                if self.should_execute_directly(safe_input):
                    viki_logger.info(
                        "FSM: SUFFICIENT REQUIREMENTS. Bypassing planning; Locking EXECUTING state."
                    )
                    self.world.state.current_phase = "EXECUTING"
                    self.world.state.execution_started = True
                else:
                    self.world.state.current_phase = "PLANNING"

            # Anti-Loop Enforcement: Planning Phase
            if self.world.state.current_phase == "PLANNING":
                self.world.state.planning_depth += 1
                if self.world.state.planning_depth > MAX_PLANNING_CYCLES:
                    viki_logger.warning(
                        "FSM: MAX_PLANNING_CYCLES exceeded. Forcing EXECUTING state."
                    )
                    self.world.state.current_phase = "EXECUTING"
                    self.world.state.execution_started = True

        # FSM State Sanitization
        if not self.world.state.current_phase:
            self.world.state.current_phase = "IDLE"

        viki_logger.info(
            f"FSM State: {self.world.state.current_phase} | Goal: {self.world.state.active_goal[:30] if self.world.state.active_goal else 'None'}..."
        )
        self.world.save()

        return await run_react_loop(
            self,
            user_input=user_input,
            safe_input=safe_input,
            session_id=session_id,
            on_event=on_event,
            on_think=on_think,
            memory_context=memory_context,
            url_context=url_context,
            world_understanding=world_understanding,
            cognitive_route=cognitive_route,
            use_lite=use_lite,
            signals_state=signals_state,
            agency_weights=agency_weights,
            project_instructions=project_instructions,
            is_continuation=is_continuation,
            task_type=task_type,
            budget=budget,
            outcome=outcome,
        )

    async def _trigger_evolution_if_needed(self, force: bool = False):
        # v11: STOP RULE FOR MODEL IMPROVEMENT
        if self._should_skip_evolution(force):
            self._handle_plateau_redirect()
            return  # Skip Model Forge

        # 1. Neural Evolution (Model Refinement)
        stable_lessons = self.learning.get_stable_lesson_count()
        current_total = self.learning.get_total_lesson_count()

        state_path = self._get_evolution_state_path()

        last_total = 0
        if os.path.exists(state_path):
            try:
                state = await asyncio.to_thread(self._read_json, state_path)
                last_total = state.get("last_forge_lesson_count", 0)
            except Exception as e:
                viki_logger.debug(f"Could not load evolution state: {e}")

        if force or (stable_lessons >= 10 and current_total - last_total >= 5):
            viki_logger.info(
                f"Initiating Neural Forge Evolution (Stable Lessons: {stable_lessons})..."
            )

            # Use the SkillRegistry to execute the Forge
            forge_skill = self.skill_registry.get_skill("internal_forge")
            if forge_skill:
                result = await forge_skill.execute({"strategy": "auto", "steps": 60})
                viki_logger.info(f"Forge Result: {result}")

                if "SUCCESS" in result:
                    await asyncio.to_thread(
                        self._write_json,
                        state_path,
                        {"last_forge_lesson_count": current_total},
                        indent=None,
                    )
            else:
                viki_logger.warning("Forge skill not found.")

        recs = self.skill_registry.get_refactor_recommendations()
        for rec in recs:
            viki_logger.warning(f"Self-Awareness Alert: {rec}")
            self.learning.save_lesson(f"INTERNAL_SYSTEM_ADVISORY: {rec}")

    def _classify_task(self, input_text: str) -> str:
        s = input_text.strip().lower()
        # v21: Explicit Question detection (use stripped text so leading UI junk does not force "general")
        if any(k in s for k in ["see", "look", "screen", "vision", "screenshot"]):
            return "vision"
        question_words = [
            "what",
            "who",
            "where",
            "when",
            "why",
            "how",
            "is",
            "are",
            "can",
            "do",
            "does",
        ]
        if s.endswith("?"):
            return "reasoning"  # questions use reasoning budget (no separate "question" key in budgets)
        if any(s == w or s.startswith(w + " ") for w in question_words):
            return "reasoning"
        from viki.core.agent_constants import CODING_KEYWORDS

        if any(k in s for k in CODING_KEYWORDS):
            return "coding"
        if any(k in s for k in ["plan", "think", "analyze", "sequence"]):
            return "reasoning"
        return "general"

    def _is_explanation_requested(self, input_text: str) -> bool:
        explanation_keywords = [
            "why",
            "explain",
            "details",
            "elaborate",
            "how",
            "what happened",
            "reason",
        ]
        return any(k in input_text.lower() for k in explanation_keywords)

    _KNOWLEDGE_GAP_MARKERS = (
        "i don't know",
        "i do not know",
        "not sure",
        "i'm not sure",
        "i am not sure",
        "cannot say",
        "can't say",
        "no information",
        "beyond my knowledge",
        "outside my knowledge",
        "not in my training",
        "i wasn't trained",
        "i was not trained",
        "unable to verify",
        "i cannot verify",
        "can't verify",
        "would need to search",
        "i don't have access to",
        "i have no access to",
        "not certain",
        "unclear to me",
        "i lack",
        "don't have current",
        "do not have current",
        "cannot find any",
        "can't find any",
    )

    def _auto_web_research_setting_enabled(self) -> bool:
        if getattr(self, "air_gap", False) or getattr(self, "shadow_mode", False):
            return False
        sys = self.settings.get("system") or {}
        return bool(sys.get("auto_web_research_when_uncertain", True))

    def _response_indicates_knowledge_gap(self, text: str) -> bool:
        if not text or len(text.strip()) < 8:
            return False
        low = text.lower()
        if "--- search results" in low or "web lookup (automatic)" in low:
            return False
        return any(m in low for m in self._KNOWLEDGE_GAP_MARKERS)

    async def _synthesize_answer_with_web_snippets(
        self, question: str, draft: str, web: str
    ) -> str | None:
        if not self.model_router or not web.strip():
            return None
        web_trunc = web[:7000] if len(web) > 7000 else web
        try:
            model = self.model_router.get_model(["reasoning"])
        except Exception:
            try:
                model = self.model_router.get_model(["general"])
            except Exception:
                return None
        messages = [
            {
                "role": "system",
                "content": (
                    "You are VIKI. The user asked a question. A draft answer may lack current facts. "
                    "Web search results follow. Write ONE updated answer: use snippets for facts, "
                    "cite source domains or URLs briefly, and do not invent details not in the snippets. "
                    "If snippets are irrelevant, say so in one sentence and keep the draft answer."
                ),
            },
            {
                "role": "user",
                "content": f"Question:\n{question}\n\nDraft answer:\n{draft}\n\nWeb results:\n{web_trunc}",
            },
        ]
        try:
            text = await asyncio.wait_for(model.chat(messages, temperature=0.25), timeout=120.0)
        except Exception as e:
            viki_logger.debug("Auto web synthesis LLM failed: %s", e)
            return None
        text = (text or "").strip()
        if len(text) < 20:
            return None
        return text

    async def _maybe_auto_web_research(
        self,
        safe_input: str,
        final_output: str,
        viki_resp: VIKIResponse | None,
        action_results: list[dict[str, Any]],
        session_id: str,
        on_event=None,
    ) -> str:
        if not self._auto_web_research_setting_enabled():
            return final_output
        if not safe_input or len(safe_input.strip()) < 8:
            return final_output

        rs = self.skill_registry.get_skill("research")
        if not rs:
            return final_output

        for r in action_results:
            act = (r.get("action") or "").lower()
            if act.startswith("research("):
                return final_output

        conf = 1.0
        if viki_resp and viki_resp.final_thought:
            try:
                conf = float(getattr(viki_resp.final_thought, "confidence", 1.0) or 1.0)
            except (TypeError, ValueError):
                conf = 1.0

        uncertain_phrase = self._response_indicates_knowledge_gap(final_output)
        if conf >= 0.5 and not uncertain_phrase:
            return final_output

        query = safe_input.strip()[:500]
        viki_logger.info(
            "Auto web research: triggered (confidence=%.2f, uncertain_phrase=%s).",
            conf,
            uncertain_phrase,
        )
        if on_event:
            on_event("status", "AUTO WEB RESEARCH (uncertain answer)")

        try:
            web = await asyncio.wait_for(rs.execute({"query": query}), timeout=28.0)
        except TimeoutError:
            viki_logger.warning("Auto web research timed out.")
            return final_output
        except Exception as e:
            viki_logger.warning("Auto web research failed: %s", e)
            return final_output

        if not web or "No results found" in web or web.startswith(("Search error", "Error:")):
            return final_output

        synthesized = await self._synthesize_answer_with_web_snippets(safe_input, final_output, web)
        if synthesized:
            meta = self._last_response_meta_by_session.get(session_id) or {}
            meta["auto_web_research"] = True
            self._last_response_meta_by_session[session_id] = meta
            return synthesized

        meta = self._last_response_meta_by_session.get(session_id) or {}
        meta["auto_web_research"] = True
        self._last_response_meta_by_session[session_id] = meta
        appendix = web[:8000] if len(web) > 8000 else web
        return f"{final_output}\n\n---\n**Web lookup (automatic)**\n{appendix}"

    def _get_skills_context(self) -> str:
        return self.skill_registry.get_context_description()

    def _compress_output(self, text: str) -> str:
        if not text:
            return text
        fillers = [
            "I will now",
            "I am going to",
            "Let me see",
            "Starting the process of",
            "Confirmed.",
            "Okay,",
            "Certainly.",
            "Processing...",
            "Executing command:",
        ]
        cleaned = text
        for f in fillers:
            cleaned = cleaned.replace(f, "").strip()
        if cleaned:
            cleaned = cleaned[0].upper() + cleaned[1:]
        return cleaned

    def attach_mcp_skills_sync(self, config_path: str | None = None) -> int:
        """
        P0 fix: actually wire MCP skills into the controller at boot time.

        Loads `viki/config/mcp_servers.yaml`, connects to each server, and
        registers every advertised tool as a `MCPSkillProxy` on the skill
        registry. Tolerates missing SDK / empty config / connection errors
        so VIKI keeps booting without MCP. Returns the count of skills
        installed (0 if disabled).
        """
        try:
            from integrations.mcp_client import attach_mcp_skills
        except Exception as e:
            viki_logger.debug("MCP wiring skipped: import failed: %s", e)
            return 0
        try:
            try:
                asyncio.get_running_loop()
                # If a loop is already running we cannot block on it; spawn a
                # background task and return immediately. Tools will register
                # asynchronously.
                asyncio.ensure_future(self._attach_mcp_async(config_path))
                return 0
            except RuntimeError:
                installed = asyncio.run(attach_mcp_skills(self, config_path))
        except Exception as e:
            viki_logger.warning("MCP wiring failed: %s", e)
            return 0
        self.mcp_skill_count = int(installed or 0)
        if self.mcp_skill_count:
            viki_logger.info("MCP: %d external tools registered as skills.", self.mcp_skill_count)
        return self.mcp_skill_count

    async def _attach_mcp_async(self, config_path: str | None = None) -> int:
        try:
            from integrations.mcp_client import attach_mcp_skills

            installed = await attach_mcp_skills(self, config_path)
        except Exception as e:
            viki_logger.debug("MCP async attach failed: %s", e)
            return 0
        self.mcp_skill_count = int(installed or 0)
        if self.mcp_skill_count:
            viki_logger.info("MCP: %d external tools registered as skills.", self.mcp_skill_count)
        return self.mcp_skill_count

    def should_execute_directly(self, text: str) -> bool:
        """v26: Sovereign Router signal analyzer.
        Returns True if the input contains sufficient signals (Intent + Framework + Product)
        to warrant an immediate implementation path, bypassing discovery phases.
        """
        s = text.lower()
        from viki.core.agent_constants import CODING_KEYWORDS

        # Signal A: Direct implementation verbs
        intents = ["create", "build", "make", "generate", "develop", "scaffold", "implement"]
        # Signal B: Modern Frameworks/Tech stack
        tech = CODING_KEYWORDS
        # Signal C: Product/Domain clarity
        products = ["app", "website", "dashboard", "frontend", "backend", "api", "ui", "script"]

        has_intent = any(i in s for i in intents)
        has_tech = any(t in s for t in tech)
        has_product = any(p in s for p in products)

        # Heuristic: 2 out of 3 signals usually mean the user knows what they want.
        signals = sum([has_intent, has_tech, has_product])
        return signals >= 2

    def _skill_action_severity(self, skill_name: str, params: dict[str, Any]) -> str:
        """Determines the risk level of an autonomous action."""
        dangerous = ["shellskill", "systemcontrolskill", "securityskill"]
        if skill_name.lower() in dangerous:
            return "destructive"

        # Heuristic for filesystem risk
        if skill_name.lower() == "filesystemskill":
            if any(
                k in str(params).lower() for k in ["delete", "remove", "overwrite", "rm ", "del "]
            ):
                return "medium"

        return "low"

    async def shutdown(self):
        if getattr(self, "_shutting_down", False):
            return
        self._shutting_down = True
        viki_logger.info("Shutting down...")

        if getattr(self, "config_watcher", None) is not None:
            self.config_watcher.stop()

        if getattr(self, "mcp_client", None) is not None:
            try:
                await self.mcp_client.disconnect_all()
            except Exception as e:
                viki_logger.debug("MCP disconnect failed: %s", e)

        try:
            self.evolution.flush()
        except Exception as e:
            viki_logger.debug(f"Evolution flush on shutdown: {e}")

        # Signal background loops to exit cleanly
        if getattr(self, "_shutdown_event", None) is not None:
            self._shutdown_event.set()

        # Cancel all background tasks
        if self._background_tasks:
            viki_logger.info(f"Cancelling {len(self._background_tasks)} background tasks...")
            for task in self._background_tasks:
                task.cancel()
            # Wait for all tasks to complete cancellation
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
            viki_logger.info("All background tasks cancelled")

        # v12: Session Narrative Synthesis
        try:
            if len(self.memory.working.get_trace()) > 4:  # Only record meaningful sessions
                viki_logger.info("Synthesizing session narrative...")
                context = self.memory.working.get_trace()
                # Create a simple summary of the interaction
                user_msg_count = sum(1 for m in context if m["role"] == "user")
                summary = f"Had a session with Orythix001 involving {user_msg_count} exchanges. "
                if any(
                    m["role"] == "assistant" and "error" in m["content"].lower() for m in context
                ):
                    summary += "We encountered some technical hurdles but optimized through them."
                else:
                    summary += (
                        "The synchronization was high and we achieved the objectives smoothly."
                    )

                self.learning.save_narrative(
                    summary, significance=0.7, mood=str(self.bio.get_state())
                )

                # Extract structured facts from session
                viki_logger.info("Analyzing session for knowledge extraction...")
                model = self.model_router.get_model(capabilities=["reasoning"])
                facts = await self.learning.analyze_session(model, context, summary)
                if facts:
                    viki_logger.info(f"Session analysis extracted {len(facts)} facts")
                else:
                    viki_logger.info("Session analysis complete — no new lessons extracted.")
        except Exception as e:
            viki_logger.error(f"Narrative synthesis failed: {e}")

        self.wellness.stop()
        self.learning.prune_old_lessons()
        # v25: Persistence cleanup
        if hasattr(self.learning, "close"):
            self.learning.close()
        if hasattr(self.memory, "close"):
            self.memory.close()
        if hasattr(self, "history") and hasattr(self.history, "close"):
            self.history.close()
        if hasattr(self.scorecard, "flush"):
            self.scorecard.flush()
        # Mark closed so __del__ → close() won't double-clean and interfere
        # with other orchestrators sharing the same database path.
        self._closed = True

    def close(self):
        """Best-effort synchronous close to prevent SQLite file locks in tests.

        Some unit tests may not fully await `shutdown()`, so we also release persistence
        resources here as a safety net (idempotent).
        """
        if getattr(self, "_closed", False):
            return
        self._closed = True

        # Persistence layers
        try:
            if hasattr(self, "learning") and hasattr(self.learning, "close"):
                self.learning.close()
        except Exception as e:
            viki_logger.debug(f"Controller close: learning close failed: {e}")

        try:
            if hasattr(self, "memory") and hasattr(self.memory, "close"):
                self.memory.close()
        except Exception as e:
            viki_logger.debug(f"Controller close: memory close failed: {e}")

        try:
            if hasattr(self, "history") and hasattr(self.history, "close"):
                self.history.close()
        except Exception as e:
            viki_logger.debug(f"Controller close: history close failed: {e}")

        # Flush any debounced state that's safe to flush without async
        try:
            if hasattr(self, "scorecard") and hasattr(self.scorecard, "flush"):
                self.scorecard.flush()
        except Exception:
            pass

        # Phase 6/7: Persistent Traces
        try:
            close_persistent_traces()
        except Exception:
            pass

    def __del__(self):
        # __del__ must never raise.
        try:
            self.close()
        except Exception:
            pass

import asyncio
import os
import re
import time
from typing import Any, cast

from viki.api.central_nexus import MessagingNexus
from viki.application.services.forge_orchestrator import ForgeOrchestrator
from viki.config.logger import viki_logger
from viki.core import command_handlers
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
from viki.core.git_context import get_git_workspace_snapshot

# Orythix Cognitive Subsystems
from viki.core.governor import EthicalGovernor
from viki.core.identity_profile import Soul
from viki.core.knowledge_gaps import KnowledgeGapDetector
from viki.core.knowledge_ingestion import LearningModule
from viki.core.layers import ConsciousnessStack
from viki.core.memory import HierarchicalMemory
from viki.core.meta_cognition import ReflectorModule

# Phase 6: Autonomy
from viki.core.mission_control import MissionControl
from viki.core.model import ModelRouter
from viki.core.orchestrator_config import ControllerConfigMixin
from viki.core.orchestrator_evolution import ControllerEvolutionMixin
from viki.core.orchestrator_helpers import (
    _LAZY_SKILL_SPECS,
)
from viki.core.orchestrator_lifecycle import ControllerLifecycleMixin
from viki.core.orchestrator_skills_mixin import ControllerSkillsMixin
from viki.core.orchestrator_telemetry import ControllerTelemetryMixin
from viki.core.output_verifier import JudgmentEngine
from viki.core.performance_benchmark import ControlledBenchmark
from viki.core.rapid_response_system import ReflexBrain
from viki.core.react_loop import run_react_loop
from viki.core.request_pipeline import RequestContext, build_default_preflight_pipeline
from viki.core.runtime_health import RuntimeHealthReporter
from viki.core.schema import VIKIResponse
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
from viki.ops.tenant_ops import ControllerTenantConnector, OpsPlan, SimpleOpsPlanner
from viki.skills.registry import SkillRegistry


class VIKIController(
    ControllerConfigMixin,
    ControllerEvolutionMixin,
    ControllerSkillsMixin,
    ControllerTelemetryMixin,
    ControllerLifecycleMixin,
):
    # Centralize default paths/tokens to avoid duplicated literals and keep behavior consistent.
    DEFAULT_DATA_DIR = "./data"
    DEFAULT_WORKSPACE_DIR = "."
    CONFIRM_TOKEN = "/confirm"
    REJECT_TOKEN = "/reject"

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
        self.tool_contract = ToolContractValidator(self.skill_registry, self.safety)
        self.health_reporter = RuntimeHealthReporter(self)
        self.capabilities = CapabilityRegistry()
        self.disabled_skills: dict[Any, Any] = {}
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
        self.active_tasks: list[Any] = []
        self.pending_actions: dict[Any, Any] = {}  # For confirmation flow, keyed by session
        self.pending_ops_plans: dict[Any, Any] = {}  # For ops approval flow, keyed by session
        self._last_response_meta_by_session: dict[Any, Any] = {}
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

    def get_differentiators(self) -> list[str]:
        """Return list of differentiators from settings (what makes VIKI specific)."""
        return cast(
            "list[str]",
            self.settings.get("system", {}).get(
                "differentiators",
                [
                    "Local Neural Forge",
                    "Orythix governance",
                    "Reflex layer",
                    "Air-gap capable",
                ],
            ),
        )

    # Skill execution timeout: min/max bounds and default budget multiplier
    SKILL_TIMEOUT_MAX = 120
    SKILL_TIMEOUT_MIN = 30
    SKILL_TIMEOUT_BUDGET_DEFAULT = 5
    SKILL_TIMEOUT_BUDGET_MULTIPLIER = 12

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
    _LAZY_SKILL_SPECS = _LAZY_SKILL_SPECS  # imported from orchestrator_helpers

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

        severity = self._skill_action_severity(skill_name, params)
        if severity in ("medium", "destructive"):
            self.pending_actions[session_id] = reflex_action_override
            return (
                f"Reflex matched '{skill_name}'. Safety Check: this is a {severity} action. "
                "Confirm to proceed, or say no to cancel."
            )

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

        import re

        _self_ref = re.search(
            r"(who\s+are\s+you|what\s+are\s+you|tell\s+me\s+about\s+(yourself|you(\s+viki)?)|"
            r"about\s+yourself|introduce\s+yourself|describe\s+yourself)",
            safe_input.lower().strip(),
        )
        if _self_ref:
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

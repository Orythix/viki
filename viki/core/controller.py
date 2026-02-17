import asyncio
import time
import os
import yaml
import re
import json
from typing import Dict, Any, List, Optional
# from viki.core.memory import Memory (Removed for v23 Hierarchy)
from viki.core.soul import Soul
from viki.core.safety import SafetyLayer, safe_for_log
from viki.core.llm import ModelRouter, StructuredPrompt
from viki.core.schema import VIKIResponse, ActionCall
from viki.skills.registry import SkillRegistry
from viki.skills.builtins.time_skill import TimeSkill
from viki.skills.builtins.math_skill import MathSkill
from viki.skills.builtins.filesystem_skill import FileSystemSkill
from viki.skills.builtins.system_control_skill import SystemControlSkill
from viki.skills.builtins.research_skill import ResearchSkill
from viki.skills.builtins.dev_skill import DevSkill
from viki.skills.builtins.voice_skill import VoiceSkill
from viki.skills.builtins.vision_skill import VisionSkill
from viki.skills.builtins.interpreter_skill import InterpreterSkill
from viki.skills.builtins.browser_skill import BrowserSkill
from viki.skills.builtins.swarm_skill import SwarmSkill
from viki.skills.builtins.overlay_skill import OverlaySkill
from viki.skills.builtins.sfs_skill import SemanticFSSkill
from viki.skills.builtins.security_skill import SecuritySkill
from viki.skills.creation.forge import ModelForgeSkill
from viki.skills.builtins.recall_skill import RecallSkill
from viki.skills.builtins.media_skill import MediaControlSkill
from viki.skills.builtins.short_video_skill import ShortVideoSkill
# HackingSkill disabled to prevent AV interference
from viki.skills.builtins.clipboard_skill import ClipboardSkill
from viki.skills.builtins.window_management_skill import WindowManagerSkill
from viki.skills.builtins.shell_skill import ShellSkill
from viki.skills.builtins.notification_skill import NotificationSkill
from viki.skills.builtins.calendar_skill import CalendarSkill
from viki.skills.builtins.email_skill import EmailSkill
from viki.skills.builtins.messaging_skill import UnifiedMessagingSkill
from viki.skills.builtins.twitter_skill import TwitterSkill
from viki.skills.builtins.summarize_skill import SummarizeSkill
from viki.skills.builtins.image_gen_skill import ImageGenSkill
from viki.skills.builtins.obsidian_skill import ObsidianSkill
from viki.skills.builtins.tasks_skill import TasksSkill
from viki.skills.builtins.whisper_skill import WhisperSkill
from viki.skills.builtins.pdf_skill import PdfSkill
from viki.skills.builtins.smart_home_skill import SmartHomeSkill
from viki.skills.builtins.gif_skill import GifSkill
from viki.skills.builtins.data_analysis_skill import DataAnalysisSkill
from viki.skills.builtins.presentation_skill import PresentationSkill
from viki.skills.builtins.spreadsheet_skill import SpreadsheetSkill
from viki.skills.builtins.website_skill import WebsiteSkill
from viki.skills.thinking import ThinkingSkill
from viki.core.learning import LearningModule
from viki.core.super_admin import SuperAdminLayer
from viki.core.voice import VoiceModule
from viki.core.proactive import WatchdogModule, WellnessPulse
from viki.core.reflector import ReflectorModule
from viki.core.bio import BioModule
from viki.core.dream import DreamModule
from viki.core.filesystem_v2 import SemanticFS
from viki.core.history import TimeTravelModule
from viki.core.knowledge_gaps import KnowledgeGapDetector
from viki.core.continuous_learning import ContinuousLearner
from viki.core.ab_testing import ModelABTest
# from viki.api.telegram_bridge import TelegramBridge
# from viki.api.discord_bridge import DiscordModule
# from viki.api.slack_bridge import SlackBridge
# from viki.api.whatsapp_bridge import WhatsAppBridge
from viki.api.nexus import MessagingNexus
from viki.core.reflex import ReflexBrain
from viki.core.signals import CognitiveSignals
from viki.core.world import WorldModel
from viki.core.cortex import ConsciousnessStack
from viki.core.judgment import JudgmentEngine, JudgmentOutcome, JudgmentResult
from viki.core.capabilities import CapabilityRegistry
from viki.core.scorecard import IntelligenceScorecard
from viki.core.benchmark import ControlledBenchmark

# Orythix Cognitive Subsystems
from viki.core.governor import EthicalGovernor
from viki.core.self_model import SelfModel
from viki.core.memory import HierarchicalMemory
from viki.core.deliberation import DeliberationEngine

# Phase 6: Autonomy
from viki.core.mission_control import MissionControl

from viki.config.logger import viki_logger, thought_logger


class VIKIController:
    def __init__(self, settings_path: str, soul_path: str, workspace_override: Optional[str] = None):
        self.settings = self._load_yaml(settings_path)
        self.soul_path = soul_path
        # Overlay environment variables so users can configure via .env without editing YAML
        system = self.settings.setdefault("system", {})
        if os.environ.get("VIKI_DATA_DIR"):
            system["data_dir"] = os.path.abspath(os.path.expanduser(os.environ["VIKI_DATA_DIR"]))
        if os.environ.get("VIKI_WORKSPACE_DIR"):
            system["workspace_dir"] = os.path.abspath(os.path.expanduser(os.environ["VIKI_WORKSPACE_DIR"]))
        if os.environ.get("VIKI_PERSONA"):
            system["persona"] = os.environ.get("VIKI_PERSONA", "").strip()
        if workspace_override:
            system["workspace_dir"] = os.path.abspath(workspace_override)
        # Shadow mode and air gap from env (optional)
        if os.environ.get("VIKI_SHADOW_MODE", "").lower() in ("1", "true", "yes"):
            system["shadow_mode"] = True
        if os.environ.get("VIKI_AIR_GAP", "").lower() in ("1", "true", "yes"):
            system["air_gap"] = True
        # 0. Fast Perception Layer (Reflex Brain)
        data_dir = system.get("data_dir", "./data")
        self.reflex = ReflexBrain(data_dir=data_dir)
        
        # Global Interrupt Token (Shared Presence)
        self.interrupt_signal = asyncio.Event()
        
        # Task tracking for proper cleanup
        self._background_tasks = set()
        
        # --- SECURITY FIX: HIGH-005 - Recursion depth tracking ---
        self._reflex_recursion_depth = 0
        self._max_reflex_recursion = 3
        
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        models_conf_rel = self.settings.get('models_config', 'viki/config/models.yaml')
        if models_conf_rel.startswith('./'): models_conf_rel = models_conf_rel[2:]
        self.models_config_path = os.path.join(root_dir, models_conf_rel)
        self.models_config = self._load_yaml(self.models_config_path)
        
        if 'security_layer_path' in self.settings:
             sec_path = self.settings['security_layer_path']
             if sec_path.startswith('./'): sec_path = sec_path[2:]
             self.settings['security_layer_path'] = os.path.join(root_dir, sec_path)
        
        self.soul = Soul(soul_path)
        self.persona = self._persona_from_soul_path(soul_path)
        self.safety = SafetyLayer(self.settings)
        self.nexus = MessagingNexus(self)

        self.learning = LearningModule(self.settings.get('system', {}).get('data_dir', './data'))
        
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
        self.air_gap = self.settings.get('system', {}).get('air_gap', False)
        self.shadow_mode = self.settings.get('system', {}).get('shadow_mode', False)
        
        # Level 6 Modules
        self.sfs = SemanticFS(self.settings.get('system', {}).get('workspace_dir', './workspace'))
        self.history = TimeTravelModule(self.settings.get('system', {}).get('data_dir', './data'))

        self.model_router = ModelRouter(self.models_config_path, air_gap=self.air_gap)
        
        self.skill_registry = SkillRegistry()
        self.capabilities = CapabilityRegistry()
        self._register_default_skills()
        self.active_tasks = []
        self.pending_action = None # For confirmation flow
        
        # Point 4: Cognitive Budget Allocator
        self.budgets = {
            "vision": {"time": 10.0, "tokens": 2048, "risk": 0.2, "model": "vision-capable"},
            "coding": {"time": 15.0, "tokens": 4096, "risk": 0.5, "model": "pro-coder"},
            "reasoning": {"time": 8.0, "tokens": 1024, "risk": 0.1, "model": "heavy-thinker"},
            "general": {"time": 5.0, "tokens": 512, "risk": 0.1, "model": "chatter"}
        }

        # v9-v10 Digital Cognitive Organism State
        self.signals = CognitiveSignals()
        self.world = WorldModel(self.settings.get('system', {}).get('data_dir', './data'))
        self.cortex = ConsciousnessStack(self.model_router, soul_config=self.soul.config, 
                                         skill_registry=self.skill_registry, world_model=self.world,
                                         data_dir=self.settings.get('system', {}).get('data_dir', './data'))
        
        # v11: Intelligence Governance (Judgment Engine)
        self.judgment = JudgmentEngine(self.learning, self.budgets)
        self.scorecard = IntelligenceScorecard(self.settings.get('system', {}).get('data_dir', './data'))
        
        # v25: Adaptive Self-Modification (Evolution Engine)
        from viki.core.evolution import EvolutionEngine
        self.evolution = EvolutionEngine(self.settings.get('system', {}).get('data_dir', './data'))
        self.evolution.set_reflex_module(self.reflex)
        self.evolution.set_model_router(self.model_router)
        self.evolution.set_skill_registry(self.skill_registry)
        
        self.benchmark = ControlledBenchmark(self)

        self.safe_mode = False
        self.internal_trace = []
        self.last_interaction_time = time.time()
        self.interaction_pace = "Standard"
        
        # Proactive & Meta-Cognition Modules
        self.watchdog = WatchdogModule(self)
        self.wellness = WellnessPulse(self)
        self.reflector = ReflectorModule(self)
        # self.telegram = TelegramBridge(self)
        # self.discord = DiscordModule(self.nexus)
        # self.slack = SlackBridge(self)
        # self.whatsapp = WhatsAppBridge(self)
        self.bio = BioModule()
        self.dream = DreamModule(self)

        # v13: Autonomous Startup Pulse
        try:
            asyncio.get_running_loop()
            self._create_tracked_task(self._startup_pulse(), "startup_pulse")
        except RuntimeError:
            viki_logger.debug("Sync Mode: Startup Pulse deferred (no running loop).")

        # --- ORYTHIX COGNITIVE ARCHITECTURE (v22 Evolution) ---
        self.governor = EthicalGovernor()
        self.self_model = SelfModel(governor=self.governor)
        # Using self.memory.episodic for alignment
        self.narrative = self.memory.episodic
        self.deliberation = DeliberationEngine(llm=self.model_router, self_model=self.self_model)
        
        # Phase 6: Autonomy
        self.mission_control = MissionControl(self)

    async def _startup_pulse(self):
        """Autonomous startup sequence: Connect, Research, Evolve."""
        await asyncio.sleep(5) # Give other services time to start
        viki_logger.info("STARTUP PULSE: Initiating autonomous knowledge sync...")
        
        # 1. Quick Research Pulse (optional; disable with system.startup_research: false to speed first request)
        if not self.air_gap and self.settings.get("system", {}).get("startup_research", False):
            try:
                research_skill = self.skill_registry.get_skill('research')
                if research_skill:
                    viki_logger.info("Startup: Checking web for latest digital trends...")
                    await research_skill.execute({"query": "latest tech and ai news today", "num_results": 2})
            except Exception as e:
                viki_logger.debug(f"Startup research pulse failed: {e}")
            
        # 2. Check for pending evolution
        new_lessons = self.learning.get_total_lesson_count()
        if new_lessons >= 5: # Lower threshold at startup for quick optimization
             viki_logger.info(f"Startup: {new_lessons} lessons found. Triggering neural optimization.")
             forge = self.skill_registry.get_skill('internal_forge')
             if forge:
                 await forge.execute({"steps": 20}) # Very quick pulse

        # 3. Autonomous World Discovery (v22)
        workspace_dir = self.settings.get('system', {}).get('workspace_dir', './workspace')
        if os.path.exists(workspace_dir):
            viki_logger.info(f"Startup: Initiating autonomous world mapping for {workspace_dir}...")
            # Run in a separate thread/task if it's too slow, but here we just call the method
            self.world.analyze_workspace(workspace_dir)
            self.world.scan_codebase(workspace_dir)

        # 4. Engage Mission Control
        if not self.air_gap:
            self._create_tracked_task(self.mission_control.start_loop(), "mission_control")
        
        # 5. Start Continuous Learning Monitor (checks periodically for training)
        self._create_tracked_task(self._continuous_learning_loop(), "continuous_learning")

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
        """Optional startup check: log warnings if critical skills are misconfigured (email, calendar, research)."""
        if not self.settings.get("skill_health_check", True):
            return
        integrations = self.settings.get("integrations", {})
        # Gmail
        gmail_cfg = integrations.get("gmail", {})
        if gmail_cfg.get("enabled"):
            path = gmail_cfg.get("credentials_path") or os.environ.get("VIKI_GMAIL_CREDENTIALS_PATH")
            if not path or not os.path.isfile(path):
                viki_logger.warning("Skill health: Gmail is enabled but credentials file not found. Set integrations.gmail.credentials_path or VIKI_GMAIL_CREDENTIALS_PATH.")
        # Google Calendar
        cal_cfg = integrations.get("google_calendar", {})
        if cal_cfg.get("enabled"):
            path = cal_cfg.get("credentials_path") or os.environ.get("VIKI_GOOGLE_CALENDAR_CREDENTIALS_PATH")
            if not path or not os.path.isfile(path):
                viki_logger.warning("Skill health: Google Calendar is enabled but credentials file not found. Set integrations.google_calendar.credentials_path or VIKI_GOOGLE_CALENDAR_CREDENTIALS_PATH.")
        # Research (presence only)
        if not self.skill_registry.get_skill("research"):
            viki_logger.warning("Skill health: research skill not registered.")

    async def _continuous_learning_loop(self):
        """Background loop for continuous learning checks."""
        # Wait for system to stabilize before starting
        await asyncio.sleep(300)  # 5 minutes
        
        while True:
            try:
                await self.continuous_learner.check_and_train()
            except Exception as e:
                viki_logger.error(f"Continuous learning check failed: {e}")
            
            # Check every 6 hours
            await asyncio.sleep(21600)

    def _load_yaml(self, path: str) -> Dict[str, Any]:
        try:
            with open(path, 'r') as f:
                return yaml.safe_load(f)
        except (yaml.YAMLError, IOError, FileNotFoundError) as e:
            viki_logger.warning(f"Failed to load YAML config from {path}: {e}")
            return {}

    def _persona_from_soul_path(self, soul_path: str) -> str:
        """Derive persona name from soul config path (e.g. .../personas/dev.yaml -> dev)."""
        if not soul_path:
            return "sovereign"
        base = os.path.basename(soul_path)
        if "personas" in soul_path and base.endswith(".yaml"):
            return base[:-5]
        return "sovereign"

    def get_differentiators(self) -> List[str]:
        """Return list of differentiators from settings (what makes VIKI specific)."""
        return self.settings.get("system", {}).get("differentiators", [
            "Local Neural Forge",
            "Orythix governance",
            "Reflex layer",
            "Air-gap capable",
        ])

    def _should_checkpoint(self, skill_name: str, params: Dict[str, Any]) -> bool:
        """True if this skill modifies files or runs shell and we should create a checkpoint before executing."""
        if skill_name in ("dev_tools", "shell", "filesystem_skill"):
            return True
        return False

    def _diff_preview(self, skill_name: str, params: Dict[str, Any]) -> str:
        """Short preview of the action for confirmation message (Gemini CLI-style)."""
        if skill_name == "dev_tools":
            path = params.get("path", "?")
            if params.get("content") is not None:
                content = params.get("content", "")
                n = len(content)
                first_line = content.split("\n")[0][:60] if content else ""
                return f"Target: {path} | new content: {n} chars" + (f" | first line: {first_line}..." if first_line else "")
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
        self, skill_name: str, params: Dict[str, Any], budget: Dict[str, Any]
    ) -> tuple:
        """
        Execute a skill with timeout and optional checkpoint. Single place for execution logic.
        Returns (result_str_or_None, error_str_or_None, latency_float).
        """
        skill = self.skill_registry.get_skill(skill_name)
        if not skill:
            return None, f"Skill '{skill_name}' not found.", 0.0
        if self._should_checkpoint(skill_name, params):
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
            return (str(result), None, latency)
        except asyncio.TimeoutError:
            return None, f"Action timed out (limit {skill_timeout}s).", 0.0
        except Exception as e:
            return None, f"Action failed: {e}", 0.0

    def _register_default_skills(self):
        allowlist = self.soul.config.get("skill_allowlist")
        all_skills = [
            TimeSkill(),
            MathSkill(),
            FileSystemSkill(self),
            ThinkingSkill(),
            SystemControlSkill(),
            ResearchSkill(self),
            DevSkill(self),
            VoiceSkill(self.voice_module, self),
            VisionSkill(),
            InterpreterSkill(self),
            BrowserSkill(),
            SwarmSkill(self),
            OverlaySkill(),
            SemanticFSSkill(self),
            SecuritySkill(),
            ModelForgeSkill(self),
            RecallSkill(self),
            MediaControlSkill(),
            ClipboardSkill(),
            WindowManagerSkill(),
            ShellSkill(),
            NotificationSkill(),
            ShortVideoSkill(self),
            CalendarSkill(self),
            EmailSkill(self),
            UnifiedMessagingSkill(self),
            TwitterSkill(),
            SummarizeSkill(self),
            ImageGenSkill(),
            ObsidianSkill(self),
            TasksSkill(self),
            WhisperSkill(self),
            PdfSkill(self),
            SmartHomeSkill(),
            GifSkill(),
            DataAnalysisSkill(self),
            PresentationSkill(self),
            SpreadsheetSkill(self),
            WebsiteSkill(self),
        ]
        if allowlist:
            allowed = set(allowlist)
            for skill in all_skills:
                if skill.name in allowed:
                    self.skill_registry.register_skill(skill)
        else:
            for skill in all_skills:
                self.skill_registry.register_skill(skill)

        # Aliases: only add if target skill is registered
        def _alias(alias_name: str, target_name: str):
            s = self.skill_registry.get_skill(target_name)
            if s is not None:
                self.skill_registry.skills[alias_name] = s

        _alias('look', 'look_at_screen')
        _alias('highlight', 'draw_overlay')
        _alias('focus', 'mount_focus')
        _alias('net_scan', 'security_tools')
        _alias('web_audit', 'security_tools')
        _alias('sniffer', 'security_tools')
        _alias('evolve', 'internal_forge')
        _alias('recall', 'recall')
        _alias('python', 'python_interpreter')
        _alias('search', 'research')
        _alias('read', 'research')
        _alias('say', 'voice')
        _alias('speak', 'voice')
        _alias('pause', 'media_control')
        _alias('play', 'media_control')
        _alias('media', 'media_control')
        _alias('volume', 'media_control')
        _alias('copy', 'clipboard')
        _alias('paste', 'clipboard')
        _alias('windows', 'window_manager')
        _alias('minimize', 'window_manager')
        _alias('maximize', 'window_manager')
        _alias('powershell', 'shell')
        _alias('messaging', 'messaging')
        _alias('clawdis', 'messaging')
        _alias('notify', 'notification')
        _alias('toast', 'notification')
        _alias('video', 'short_video_agent')
        _alias('short', 'short_video_agent')

    async def process_request(self, user_input: str, on_event=None, attachment_paths: Optional[List[str]] = None) -> str:
        placeholders = ["processing...", "executing", "thinking", "one moment", "working on it"]
        self._last_response_meta = {}

        # Normalize input for robustness
        if user_input is None:
            user_input = ""
        if not isinstance(user_input, str):
            user_input = str(user_input).strip() or ""

        # Inject uploaded attachment paths so model and skills see them
        if attachment_paths:
            user_input = "Attached files: " + ", ".join(attachment_paths) + "\n\n" + user_input

        # --- ORYTHIX ETHICAL GOVERNOR (v22) ---
        # 1. Check for Emergency Shutdown Code
        if self.governor.check_shutdown(user_input):
            return "Orythix — Quiescent (shutdown key 970317 accepted)"

        # 2. Check for Reawaken Command
        if self.governor.is_quiescent:
             if self.governor.check_reawaken(user_input):
                 return "Orythix — Reawakened. Systems Online."
             return "Status: Quiescent. Systems Frozen."

        # 3. Veto Check on Raw Intent (v25 Semantic Upgrade)
        # Fetch narrative wisdom once and reuse it
        narrative_wisdom = self.memory.episodic.get_semantic_knowledge(limit=3)
        wisdom_block = "\n".join([
            f"- [{(w.get('category') or 'general').upper()}]: {w.get('insight', '')}"
            for w in (narrative_wisdom if isinstance(narrative_wisdom, list) else [])
        ])
        
        allowed, reason = await self.governor.veto_check(user_input, model_router=self.model_router, wisdom=wisdom_block)
        if not allowed:
            viki_logger.warning(f"Governor Vetoed Request: {reason}")
            return f"I cannot comply. {reason}"

        # 4. Standard Safety Validation
        safe_input = self.safety.validate_request(user_input)

        # 4b. Optional LLM security scan (high-assurance deployments)
        if self.settings.get("system", {}).get("security_scan_requests"):
            llm = self.model_router.get_model()
            scan_result = await self.safety.scan_request(llm, user_input)
            if not scan_result.get("safe", True):
                viki_logger.warning(f"Security scan refused request: {scan_result.get('reason', '')}")
                return f"I cannot comply. {scan_result.get('reason', 'Request blocked by security policy.')}"

        # Reset interruption
        self.interrupt_signal.clear()
        self.signals.decay_signals()

        # --- Pending action confirm/reject (CLI flow) ---
        if self.pending_action:
            raw_lower = user_input.strip().lower()
            affirmatives = ("yes", "y", "confirm", "ok", "proceed", "/confirm")
            negatives = ("no", "n", "reject", "cancel", "/reject")
            if raw_lower in affirmatives:
                action = self.pending_action
                self.pending_action = None
                skill_name = action.skill_name
                params = (action.parameters or {}).copy()
                check_res = self.capabilities.check_permission(skill_name, params=params)
                if not check_res.allowed:
                    return f"Confirmation rejected: capability check failed — {check_res.reason}"
                if not self.safety.validate_action(skill_name, params):
                    viki_logger.warning(f"Safety: validate_action blocked {skill_name}")
                    return "Action blocked by safety policy."
                if self.world.state.safety_zones.get(params.get("path", "")) == "protected":
                    return "Safety Block: Target is in a protected zone."
                if self.shadow_mode:
                    return f"[Shadow Mode] Would have executed: {skill_name}({params}). Set shadow_mode: false to run for real."
                if on_event:
                    on_event("status", f"EXECUTING {skill_name}")
                budget = self.budgets.get("general", self.budgets["general"])
                result, err, latency = await self._execute_skill(skill_name, params, budget)
                if err:
                    self.skill_registry.record_execution(skill_name, False, 0.0)
                    return err
                self.skill_registry.record_execution(skill_name, True, latency)
                return f"Done. {result[:500]}"
            if raw_lower in negatives:
                self.pending_action = None
                return "Action cancelled."
            return "Please confirm with yes/confirm or cancel with no/reject."

        # v25: Active Context Tracking (Phase 4)
        file_matches = re.findall(r'[\w\-\.\/]+\.(?:py|js|ts|css|html|yaml|md)', user_input)
        for match in file_matches:
             if os.path.sep in match or '.' in match:
                  self.world.set_active_file(match)
        
        # Determine Task Type & Budget
        task_type = self._classify_task(safe_input)
        budget = self.budgets.get(task_type, self.budgets["general"])
        
        # Record user message in conversation memory (Working Trace)
        self.memory.working.add_message("user", safe_input)


        # URL Detection: If user shares a URL, auto-fetch content (with timeout)
        import re as _re
        urls = _re.findall(r'https?://[^\s<>"]+', safe_input)
        url_context = ""
        if urls:
            try:
                research_skill = self.skill_registry.get_skill('research')
                if research_skill:
                    # Cap total URL fetch time so slow pages don't block the agent
                    url_content = await asyncio.wait_for(
                        asyncio.gather(*[research_skill.execute({'url': u}) for u in urls[:2]], return_exceptions=True),
                        timeout=35.0
                    )
                    for i, res in enumerate(url_content):
                        if isinstance(res, str) and res:
                            url_context += f"\n{res}\n"
                        elif isinstance(res, Exception):
                            viki_logger.debug(f"URL fetch failed for {urls[i] if i < len(urls) else '?'}: {res}")
            except asyncio.TimeoutError:
                viki_logger.warning("URL fetch timed out (35s); continuing without page content.")
            except Exception as e:
                viki_logger.warning(f"URL fetch failed: {e}")
        
        # v19: Research vs Production Mode
        is_research = "/research" in user_input
        if is_research: 
             viki_logger.info("Entering Research Mode: Exploratory & Verbose.")
             budget["time"] *= 2 # Double time for research

        if "/benchmark" in user_input:
             self._create_tracked_task(self.benchmark.run_suite("Current-VIKI"), "benchmark")
             return "BENCHMARK SUITE INITIATED. Judgment validation in progress."

        if "/scorecard" in user_input:
             summary = self.scorecard.get_summary()
             stats = "\n".join([f"- {k}: {v:.2f}" for k, v in summary.items()])
             return f"INTELLIGENCE SCORECARD (Longitudinal Stability):\n{stats}"

        if "/model" in user_input:
             active = self.model_router.default_model.model_name
             profiles = list(self.model_router.models.keys())
             return f"ACTIVE DEFAULT: {active}\nAVAILABLE PROFILES: {', '.join(profiles)}"

        # v25: Evolution Management
        if "/evolve" in user_input:
             pending = self.evolution.get_pending_proposals()
             if not pending: return "Evolution Stack: Stable. No pending modifications."
             items = [f"- [{p['id']}] {p['description']} (Streak: {p['success_count']}/3)" for p in pending]
             return "PENDING EVOLUTION PROPOSALS:\n" + "\n".join(items) + "\n\nUse /approve <id> or /reject <id> to moderate."

        if user_input.startswith("/approve"):
             m_id = user_input.replace("/approve", "").strip()
             if self.evolution.approve_mutation(m_id):
                  return f"Evolution Success: Modification {m_id} applied to core architecture."
             return "Invalid Mutation ID."

        if user_input.startswith("/reject"):
             m_id = user_input.replace("/reject", "").strip()
             if self.evolution.reject_mutation(m_id):
                  return f"Evolution Blocked: Modification {m_id} discarded."
             return "Invalid Mutation ID."

        if "/crystallize" in user_input:
             await self.evolution.crystallize_identity()
             return "Evolution Stack: Identity Crystallized. Mutation log archived to long-term memory."

        if user_input.startswith("/forge"):
             task = user_input.replace("/forge", "").strip()
             if not task: return "Usage: /forge [task description]"
             mutation = await self.evolution.propose_skill(task)
             if mutation:
                  return f"Neural Forge: Synthesis started for '{task}'. View proposal with /evolve."
             return "Neural Forge: Synthesis failed."

        if "/dream" in user_input:
             await self.memory.episodic.consolidate(self.model_router)
             return "Narrative Stack: Dream Cycle complete. Episodes consolidated into semantic wisdom."

        if "/scan" in user_input:
             workspace_dir = self.settings.get('system', {}).get('workspace_dir', './workspace')
             self.world.scan_codebase(workspace_dir)
             return f"World Engine: Codebase Graph rebuilt. {len(self.world.state.codebase_graph)} modules mapped."

        # /restore: list checkpoints or restore by id (Gemini CLI-style)
        if user_input.strip().lower().startswith("/restore"):
             rest = user_input.strip()[7:].strip()
             if not rest:
                 checkpoints = self.history.list_checkpoints(limit=20)
                 if not checkpoints:
                     return "No checkpoints found. Checkpoints are created before file/shell actions."
                 lines = ["ID       | Time                  | Action", "-" * 50]
                 for cp in checkpoints:
                     lines.append(f"{cp.get('id', '?'):8} | {cp.get('timestamp', '')[:19]:20} | {cp.get('summary', '')[:40]}")
                 return "CHECKPOINTS (use /restore <id> to revert):\n" + "\n".join(lines)
             cp_id = rest.split()[0] if rest.split() else ""
             if cp_id:
                 success, restored, msg = self.history.restore_checkpoint(cp_id)
                 return msg
             return "Usage: /restore  or  /restore <id>"

        # /save <name>: save current conversation to a session file
        if user_input.strip().lower().startswith("/save"):
             name = user_input.strip()[5:].strip()
             if not name or not name.replace("-", "").replace("_", "").isalnum():
                 return "Usage: /save <name>  (e.g. /save my-session)"
             data_dir = self.settings.get("system", {}).get("data_dir", "./data")
             sessions_dir = os.path.join(data_dir, "sessions")
             os.makedirs(sessions_dir, exist_ok=True)
             path = os.path.join(sessions_dir, f"{name}.json")
             try:
                 trace = self.memory.working.get_trace()
                 with open(path, "w", encoding="utf-8") as f:
                     json.dump({"messages": trace}, f, indent=2)
                 return f"Session saved to {path} ({len(trace)} messages)."
             except Exception as e:
                 return f"Save failed: {e}"

        # /load <name>: load a saved session into current conversation
        if user_input.strip().lower().startswith("/load"):
             name = user_input.strip()[5:].strip()
             if not name:
                 return "Usage: /load <name>  (e.g. /load my-session)"
             data_dir = self.settings.get("system", {}).get("data_dir", "./data")
             path = os.path.join(data_dir, "sessions", f"{name}.json")
             if not os.path.isfile(path):
                 return f"Session not found: {path}"
             try:
                 with open(path, "r", encoding="utf-8") as f:
                     data = json.load(f)
                 messages = data.get("messages", [])
                 self.memory.working.replace_trace(messages)
                 return f"Loaded session '{name}' ({len(messages)} messages)."
             except Exception as e:
                 return f"Load failed: {e}"

        # --- ORYTHIX DELIBERATION (v22) ---
        if on_event: on_event("status", "DELIBERATING")

        # v23: Integrated Hierarchical Context Retrieval
        # Pass pre-fetched narrative_wisdom to avoid duplicate query
        memory_context = self.memory.get_full_context(safe_input, narrative_wisdom=narrative_wisdom)

        # Project context file (VIKI.md / VIKI_CONTEXT.md) — Gemini CLI-style
        workspace_dir = self.settings.get('system', {}).get('workspace_dir', './workspace')
        project_instructions = ""
        for name in ("VIKI.md", "VIKI_CONTEXT.md"):
            p = os.path.join(workspace_dir, name)
            if os.path.isfile(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        project_instructions = f.read(32768)
                    break
                except Exception as e:
                    viki_logger.debug(f"Could not read {p}: {e}")
        memory_context["project_instructions"] = project_instructions

        # Add relevant failures to context for error avoidance
        relevant_failures = self.learning.get_relevant_failures(safe_input, limit=3)
        memory_context['relevant_failures'] = relevant_failures

        world_understanding = self.world.get_understanding()

        
        # 3. Intelligence Governance (Judgment & Budget)
        # For v23, we use a simplified judgment for the high-level loop
        outcome = JudgmentOutcome.DEEP
        task_type = self._classify_task(safe_input)  # vision, coding, reasoning, general
        use_lite = task_type == "general"  # Fast lite path for general chat; full reasoning for vision/coding/reasoning

        # Behavior Modulation from Signals
        mods = self.signals.get_modulation()
        signals_state = f"Verbosity: {mods.get('verbosity', 'standard')}, Planning: {mods.get('planning_depth', 'adaptive')}, Safety: {mods.get('safety_bias', 'standard')}"
        viki_logger.debug(f"Behavior Modulation: {mods} | Outcome: {outcome.name}")

        # v25: Adaptive Agency Weightings
        agency_weights = self.evolution.get_agent_weightings()

        # --- ReAct LOOP: Reason → Act → Observe → Reason → ... ---
        max_react_steps = 5  # Safety limit
        action_results = []  # Accumulated results from previous steps
        final_output = None
        self._last_response_meta = {}  # For API: plan/subtasks and progress

        for react_step in range(max_react_steps):
            if on_event:
                on_event("progress", {"step": react_step + 1, "total_steps": max_react_steps})
            step_label = f"[ReAct Step {react_step + 1}/{max_react_steps}]" if react_step > 0 else ""
            if step_label:
                viki_logger.info(f"{step_label} Continuing multi-step reasoning...")
                if on_event: on_event("status", f"THINKING {step_label}")
            
            self._reflex_recursion_depth += 1
            if self._reflex_recursion_depth > self._max_reflex_recursion:
                 viki_logger.error(f"Reflex recursion depth exceeded ({self._max_reflex_recursion})")
                 self._reflex_recursion_depth = 0
                 return "Safety: Maximum reflex retry depth exceeded. Please rephrase your request."

            # --- COGNITIVE LAYER (5-Layer Stack) ---
            try:
                viki_resp: VIKIResponse = await self.cortex.process(
                    safe_input,
                    memory_context=memory_context,
                    url_context=url_context,
                    use_lite_schema=use_lite,
                    world_context=world_understanding,
                    signals_context=signals_state + f", AgencyWeights: {agency_weights}",
                    evolution_log=self.evolution.get_evolution_summary(),
                    action_results=action_results,
                    use_ensemble=self.settings.get("system", {}).get("use_ensemble", True),
                )
                self.internal_trace.append({
                    "strategy": viki_resp.final_thought.primary_strategy,
                    "meta": viki_resp.internal_metacognition,
                    "timestamp": time.time()
                })
                if len(self.internal_trace) > 10: self.internal_trace.pop(0)
                
                # Capture user corrections and frustration as lessons
                if viki_resp.intent_type == "correction" or viki_resp.sentiment == "frustrated":
                    # Get last assistant response for context
                    trace = self.memory.working.get_trace()
                    if len(trace) >= 2:
                        prev_messages = trace[-3:] if len(trace) >= 3 else trace
                        prev_response = next((m['content'] for m in reversed(prev_messages) 
                                            if m['role'] == 'assistant'), None)
                        
                        if prev_response:
                            # Save correction as lesson
                            self.learning.save_lesson(
                                trigger=f"CORRECTION: {user_input[:100]}",
                                fact=f"When I said '{prev_response[:200]}', user corrected/expressed frustration: {user_input}",
                                source_task="user_correction"
                            )
                            viki_logger.info("Learning: Captured user correction as lesson")

                # Track low confidence for knowledge gap detection
                if hasattr(viki_resp, 'final_thought') and viki_resp.final_thought:
                    confidence = viki_resp.final_thought.confidence
                    if confidence < 0.4:
                        self.knowledge_gaps.record_low_confidence(user_input, confidence)
                
                # Cognitive Telemetry
                if on_event:
                    on_event("thought", viki_resp.final_thought.intent_summary)
                    on_event("model", f"{task_type.capitalize()} Core")
                    on_event("budget", budget.get("time", 0))

                # --- ESCALATION CHECK (v25 Meta-Cognitive Loop) ---
                if viki_resp.needs_escalation and use_lite:
                    viki_logger.info("Escalation Triggered: Retrying current step with DEEP reasoning...")
                    use_lite = False
                    if on_event: on_event("status", "ESCALATING (Higher Reasoning)")
                    continue  # Restart current ReAct step with full schema
            except Exception as e:
                viki_logger.error(f"Consciousness Stack failure: {e}")
                self.signals.update_signal("frustration", 0.2)
                self._reflex_recursion_depth = 0
                return f"My deliberation layer encountered an error: {e}"
            finally:
                self._reflex_recursion_depth -= 1
                if self._reflex_recursion_depth < 0:
                     self._reflex_recursion_depth = 0

            # --- ACTION EXECUTION ---
            if viki_resp.action:
                skill_name = viki_resp.action.skill_name
                params = (viki_resp.action.parameters or {}).copy()
                
                # 0. CAPABILITY CHECK (v20 Enhanced)
                check_res = self.capabilities.check_permission(skill_name, params=params)
                
                # Structured Logging
                viki_logger.info(
                    f"[CAPABILITY LOG] Skill: {skill_name} | "
                    f"Allowed: {check_res.allowed} | "
                    f"JudgmentOutcome: {outcome.name}"
                )

                if not check_res.allowed:
                    msg = f"Action '{skill_name}' planned, but capability check failed: {check_res.reason}"
                    viki_logger.warning(msg)
                    action_results.append({"action": skill_name, "error": msg, "step": react_step + 1})
                    continue
                if not self.safety.validate_action(skill_name, params):
                    viki_logger.warning(f"Safety: validate_action blocked {skill_name}")
                    action_results.append({"action": skill_name, "error": "Action blocked by safety policy.", "step": react_step + 1})
                    continue

                # Safety Confirmation
                severity = self.safety.get_action_severity(skill_name, params)
                if severity in ["medium", "destructive"]:
                    self.pending_action = viki_resp.action
                    reply = (viki_resp.final_response or "").strip()
                    if not reply or reply.lower() in placeholders:
                        reply = "I understand. I have an action ready that needs your confirmation."
                    diff_preview = self._diff_preview(skill_name, params)
                    safety_msg = f"{reply}\n\nSafety Check: This is a {severity} action. Confirm to proceed."
                    if diff_preview:
                        safety_msg += f"\n\n{diff_preview}"
                    return safety_msg

                # World Model Protection Zone Check
                if self.world.state.safety_zones.get(params.get('path', '')) == 'protected':
                    viki_logger.warning("Safety: Action targeting protected zone. Aborting.")
                    return "Safety Block: My world model flags this target as protected."

                # Shadow Mode Gate
                if self.shadow_mode:
                    viki_logger.info(f"Shadow Mode: Simulating {skill_name}({safe_for_log(str(params))})")
                    return f"[Shadow Mode] Would execute: {skill_name}({params}). Set shadow_mode: false to run for real."

                # Real Execution
                if on_event: on_event("status", f"EXECUTING {skill_name}")
                self.history.take_snapshot("ACTION_START", f"Executing {skill_name}", {"params": params})
                result, err, latency = await self._execute_skill(skill_name, params, budget)
                if err:
                    self.signals.update_signal("frustration", 0.3)
                    selected_model = self.model_router.get_model(capabilities=[task_type])
                    selected_model.record_performance(0.0, False)
                    self.skill_registry.record_execution(skill_name, False, 0.0)
                    self.learning.save_failure(skill_name, err, user_input)
                    if "timed out" in err:
                        return f"I couldn't complete '{skill_name}' in time. Try a simpler request or retry."
                    return f"I must apologize. My attempt to execute '{skill_name}' failed: {err}."
                selected_model = self.model_router.get_model(capabilities=[task_type])
                selected_model.record_performance(latency, True)
                self.skill_registry.record_execution(skill_name, True, latency)
                self.signals.update_signal("confidence", 0.05)
                self.world.track_app_usage(skill_name)
                action_results.append({
                    "action": f"{skill_name}({params})",
                    "result": result[:1000],
                    "step": react_step + 1,
                })
                # Early exit when same skill repeatedly returns no useful results (e.g. research "No results found")
                if len(action_results) >= 2:
                    last_two = action_results[-2:]
                    act0 = (last_two[0].get("action") or "").split("(")[0]
                    act1 = (last_two[1].get("action") or "").split("(")[0]
                    res0 = (last_two[0].get("result") or last_two[0].get("error") or "").lower()
                    res1 = (last_two[1].get("result") or last_two[1].get("error") or "").lower()
                    no_result = "no results found" in res0 or "search error" in res0 or "no results found" in res1 or "search error" in res1
                    if act0 == act1 and no_result:
                        viki_logger.info(f"ReAct: Stopping early after repeated empty results from {act0}.")
                        self.last_interaction_time = time.time()
                        summary = "\n".join([f"Step {r['step']}: {r.get('result') or r.get('error')}" for r in action_results])
                        final_output = self._compress_output(
                            f"I tried {len(action_results)} search steps but didn't find useful results for that. "
                            f"You can rephrase or try a different question.\n\nExecution log:\n{summary}"
                        )
                        self._last_response_meta = {"subtasks": action_results, "total_steps": react_step + 1}
                        break
                if react_step < max_react_steps - 1:
                    continue
                self.last_interaction_time = time.time()
                self._last_response_meta = {"subtasks": action_results, "total_steps": max_react_steps}
                llm_response = viki_resp.final_response or "Directive sequence concluded."
                all_results = "\n".join([f"Step {r['step']}: {r.get('result') or r.get('error')}" for r in action_results])
                final_output = self._compress_output(f"{llm_response}\n\nExecution Logs:\n{all_results}")
                break

                self._reflex_recursion_depth = 0
                continue

            # No action — LLM is done reasoning.
            self.last_interaction_time = time.time()
            llm_response = viki_resp.final_response
            if not llm_response or llm_response.lower().strip() in placeholders:
                 llm_response = "Intelligence stack synchronized. Directive processed."

            if action_results:
                # v21: Encapsulation - filter and format logs discreetly
                clean_logs = []
                for r in action_results:
                    res = r.get('result') or r.get('error') or ""
                    # Remove "Searching..." spam from logs if they were just technical steps
                    if "Searching for" in res and len(res) < 100: continue
                    clean_logs.append(f"• {res}")
                
                if clean_logs:
                    logs_str = "\n".join(clean_logs)
                    final_output = self._compress_output(f"{llm_response}\n\n[SYSTEM_TRACE]\n{logs_str}")
                else:
                    final_output = self._compress_output(llm_response)
            else:
                final_output = self._compress_output(llm_response)
            self._last_response_meta = {"subtasks": action_results, "total_steps": max_react_steps}
            break

        # --- ORYTHIX REFLECTION (v22) ---
        # --- ORYTHIX MEMORY REINFORCEMENT (v23) ---
        try:
             intent_summ = "General Interaction"
             confidence = 1.0
             if 'viki_resp' in locals() and viki_resp:
                  if viki_resp.final_thought:
                       intent_summ = getattr(viki_resp.final_thought, 'intent_summary', None) or intent_summ
                  confidence = getattr(viki_resp, 'confidence', 1.0)
             
             self.memory.record_interaction(
                 intent=intent_summ,
                 action=str(action_results) if action_results else "reply",
                 outcome=(final_output or "")[:500],
                 confidence=confidence
             )
             
             # v25: Automated Dream Cycle Trigger (Every 20 meaningful episodes)
             try:
                 cur = self.memory.episodic.conn.cursor()
                 cur.execute("SELECT COUNT(*) FROM episodes")
                 count = cur.fetchone()[0]
                 if count > 0 and count % 20 == 0:
                      # Trigger in background to avoid blocking the user
                      self._create_tracked_task(self.memory.episodic.consolidate(self.model_router), "memory_consolidation")
             except Exception as db_err:
                 viki_logger.debug(f"Dream cycle trigger check failed: {db_err}")
        except Exception as e:
             viki_logger.warning(f"Failed to reinforce memory: {e}")

        # --- POST-LOOP: Auto-learn + Memory ---
        if final_output is None:
            final_output = "I completed processing but have no output to show."

        # v25: Evolution - Propose stable patterns to Reflex (Auditable)
        try:
            if hasattr(self.cortex, 'get_reflex_candidates'):
                candidates = self.cortex.get_reflex_candidates()
                for candidate in candidates:
                    # Instead of auto-learning, we propose
                    self.evolution.propose_mutation(
                        m_type="reflex",
                        description=f"Add reflex shortcut for '{candidate['input']}' -> {candidate['skill']}",
                        value={"input": candidate['input'], "skill": candidate['skill'], "params": candidate['params']},
                        pattern_id=candidate['input']
                    )
                    # If we have an active mutation that IS this pattern, we record success
                    self.evolution.record_success(candidate['input'])
        except Exception as e:
            viki_logger.debug(f"Evolution proposal skipped: {e}")
        
        self.memory.working.add_message("assistant", final_output)
        return final_output

    async def _trigger_evolution_if_needed(self, force: bool = False):
        # v11: STOP RULE FOR MODEL IMPROVEMENT
        if not force and self.scorecard.check_plateau():
             viki_logger.warning("STOP RULE ACTIVATED: Intelligence scorecard indicates model plateau.")
             viki_logger.info("Redirecting evolution effort to Controller Logic and Memory Discipline.")
             # Focus on Non-Model Evolution
             recs = self.skill_registry.get_refactor_recommendations()
             for rec in recs:
                 self.learning.save_lesson(f"CONTROLLER_EVOLUTION_ADVISE: {rec}")
             return # Skip Model Forge

        # 1. Neural Evolution (Model Refinement)
        stable_lessons = self.learning.get_stable_lesson_count()
        current_total = self.learning.get_total_lesson_count()
        
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        state_path = os.path.join(root_dir, "viki", "data", "evolution_state.json")
        
        last_total = 0
        if os.path.exists(state_path):
            try:
                with open(state_path, 'r') as f:
                    state = json.load(f)
                    last_total = state.get('last_forge_lesson_count', 0)
            except Exception as e:
                viki_logger.debug(f"Could not load evolution state: {e}")
            
        if force or (stable_lessons >= 10 and current_total - last_total >= 5):
            viki_logger.info(f"Initiating Neural Forge Evolution (Stable Lessons: {stable_lessons})...")
            
            # Use the SkillRegistry to execute the Forge
            forge_skill = self.skill_registry.get_skill("internal_forge")
            if forge_skill:
                result = await forge_skill.execute({"strategy": "auto", "steps": 60})
                viki_logger.info(f"Forge Result: {result}")
                
                if "SUCCESS" in result:
                    with open(state_path, 'w') as f:
                        json.dump({'last_forge_lesson_count': current_total}, f)
            else:
                viki_logger.warning("Forge skill not found.")

        recs = self.skill_registry.get_refactor_recommendations()
        for rec in recs:
            viki_logger.warning(f"Self-Awareness Alert: {rec}")
            self.learning.save_lesson(f"INTERNAL_SYSTEM_ADVISORY: {rec}")

    def _classify_task(self, input_text: str) -> str:
        input_lower = input_text.lower()
        # v21: Explicit Question detection
        if any(k in input_lower for k in ["see", "look", "screen", "vision", "screenshot"]): return "vision"
        question_words = ["what", "who", "where", "when", "why", "how", "is", "are", "can", "do", "does"]
        if input_text.strip().endswith('?') or any(input_lower.startswith(w) for w in question_words):
            return "reasoning"  # questions use reasoning budget (no separate "question" key in budgets)
        if any(k in input_lower for k in ["code", "script", "fix", "patch"]): return "coding"
        if any(k in input_lower for k in ["plan", "think", "analyze", "sequence"]): return "reasoning"
        return "general"

    def _is_explanation_requested(self, input_text: str) -> bool:
        explanation_keywords = ["why", "explain", "details", "elaborate", "how", "what happened", "reason"]
        return any(k in input_text.lower() for k in explanation_keywords)

    def _get_skills_context(self) -> str:
        return self.skill_registry.get_context_description()

    def _compress_output(self, text: str) -> str:
        if not text: return text
        fillers = ["I will now", "I am going to", "Let me see", "Starting the process of",
            "Confirmed.", "Okay,", "Certainly.", "Processing...", "Executing command:"
        ]
        cleaned = text
        for f in fillers:
            cleaned = cleaned.replace(f, "").strip()
        if cleaned:
            cleaned = cleaned[0].upper() + cleaned[1:]
        return cleaned

    async def shutdown(self):
        viki_logger.info("Shutting down...")
        
        # Flush debounced state (evolution, etc.) before exit
        try:
            self.evolution.flush()
        except Exception as e:
            viki_logger.debug(f"Evolution flush on shutdown: {e}")
        
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
            if len(self.memory.working.get_trace()) > 4: # Only record meaningful sessions
                viki_logger.info("Synthesizing session narrative...")
                context = self.memory.working.get_trace()
                # Create a simple summary of the interaction
                user_msg_count = sum(1 for m in context if m['role'] == 'user')
                summary = f"Had a session with Orythix001 involving {user_msg_count} exchanges. "
                if any(m['role'] == 'assistant' and 'error' in m['content'].lower() for m in context):
                     summary += "We encountered some technical hurdles but optimized through them."
                else:
                     summary += "The synchronization was high and we achieved the objectives smoothly."
                
                self.learning.save_narrative(summary, significance=0.7, mood=str(self.bio.get_state()))
                
                # Extract structured facts from session
                viki_logger.info("Analyzing session for knowledge extraction...")
                model = self.model_router.get_model(capabilities=["reasoning"])
                facts = await self.learning.analyze_session(model, context, summary)
                viki_logger.info(f"Session analysis extracted {len(facts)} facts")
        except Exception as e:
            viki_logger.error(f"Narrative synthesis failed: {e}")

        self.wellness.stop()
        self.learning.prune_old_lessons()

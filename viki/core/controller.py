import asyncio
import time
import os
import yaml
import re
import json
from typing import Dict, Any, List, Optional
# from viki.core.memory import Memory (Removed for v23 Hierarchy)
from viki.core.soul import Soul
from viki.core.safety import SafetyLayer
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
from viki.core.memory import NarrativeMemory
from viki.core.deliberation import DeliberationEngine

# Phase 6: Autonomy
from viki.core.mission_control import MissionControl

from viki.config.logger import viki_logger, thought_logger


class VIKIController:
    def __init__(self, settings_path: str, soul_path: str):
        self.settings = self._load_yaml(settings_path)
        
        # 0. Fast Perception Layer (Reflex Brain)
        data_dir = self.settings.get('system', {}).get('data_dir', './data')
        self.reflex = ReflexBrain(data_dir=data_dir)
        
        # Global Interrupt Token (Shared Presence)
        self.interrupt_signal = asyncio.Event()
        
        # Task tracking for proper cleanup
        self._background_tasks = set()
        
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
        self.safety = SafetyLayer(self.settings)
        self.nexus = MessagingNexus(self)

        self.learning = LearningModule(self.settings.get('system', {}).get('data_dir', './data'))
        
        # v25: Knowledge Gap Detection
        self.knowledge_gaps = KnowledgeGapDetector(self.learning)
        
        # v25: A/B Testing and Continuous Learning
        self.ab_tester = ModelABTest(self)
        self.continuous_learner = ContinuousLearner(self)
        
        # v23: Hierarchical Memory Stack (Orythix Standard)
        from viki.core.memory import HierarchicalMemory
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
        
        # 1. Quick Research Pulse
        if not self.air_gap:
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

    def _register_default_skills(self):
        self.skill_registry.register_skill(TimeSkill())
        self.skill_registry.register_skill(MathSkill())
        self.skill_registry.register_skill(FileSystemSkill())
        self.skill_registry.register_skill(ThinkingSkill())
        self.skill_registry.register_skill(SystemControlSkill())
        self.skill_registry.register_skill(ResearchSkill(self))
        self.skill_registry.register_skill(DevSkill())
        self.skill_registry.register_skill(VoiceSkill(self.voice_module))
        self.skill_registry.register_skill(VisionSkill())
        self.skill_registry.register_skill(InterpreterSkill())
        self.skill_registry.register_skill(BrowserSkill())
        self.skill_registry.register_skill(SwarmSkill(self))
        self.skill_registry.register_skill(OverlaySkill())
        self.skill_registry.register_skill(SemanticFSSkill(self))
        self.skill_registry.register_skill(SecuritySkill())
        self.skill_registry.register_skill(ModelForgeSkill(self))
        self.skill_registry.register_skill(RecallSkill(self))
        self.skill_registry.register_skill(MediaControlSkill())
        self.skill_registry.register_skill(ClipboardSkill())
        self.skill_registry.register_skill(WindowManagerSkill())
        self.skill_registry.register_skill(ShellSkill())
        self.skill_registry.register_skill(NotificationSkill())
        self.skill_registry.register_skill(ShortVideoSkill(self))
        # self.skill_registry.register_skill(HackingSkill()) # Disabled due to system-level safety blocks

        # Aliases for natural language routing
        self.skill_registry.skills['look'] = self.skill_registry.get_skill('look_at_screen')
        self.skill_registry.skills['highlight'] = self.skill_registry.get_skill('draw_overlay')
        self.skill_registry.skills['focus'] = self.skill_registry.get_skill('mount_focus')
        self.skill_registry.skills['net_scan'] = self.skill_registry.get_skill('security_tools')
        self.skill_registry.skills['web_audit'] = self.skill_registry.get_skill('security_tools')
        self.skill_registry.skills['sniffer'] = self.skill_registry.get_skill('security_tools')
        self.skill_registry.skills['evolve'] = self.skill_registry.get_skill('internal_forge')
        self.skill_registry.skills['recall'] = self.skill_registry.get_skill('recall')

        self.skill_registry.skills['python'] = self.skill_registry.get_skill('python_interpreter')
        self.skill_registry.skills['search'] = self.skill_registry.get_skill('research')
        self.skill_registry.skills['read'] = self.skill_registry.get_skill('research')
        self.skill_registry.skills['say'] = self.skill_registry.get_skill('voice')
        self.skill_registry.skills['speak'] = self.skill_registry.get_skill('voice')

        # Media control aliases
        self.skill_registry.skills['pause'] = self.skill_registry.get_skill('media_control')
        self.skill_registry.skills['play'] = self.skill_registry.get_skill('media_control')
        self.skill_registry.skills['media'] = self.skill_registry.get_skill('media_control')
        self.skill_registry.skills['volume'] = self.skill_registry.get_skill('media_control')
        
        # New aliases
        self.skill_registry.skills['copy'] = self.skill_registry.get_skill('clipboard')
        self.skill_registry.skills['paste'] = self.skill_registry.get_skill('clipboard')
        self.skill_registry.skills['windows'] = self.skill_registry.get_skill('window_manager')
        self.skill_registry.skills['minimize'] = self.skill_registry.get_skill('window_manager')
        self.skill_registry.skills['maximize'] = self.skill_registry.get_skill('window_manager')
        self.skill_registry.skills['powershell'] = self.skill_registry.get_skill('shell')
        self.skill_registry.skills['notify'] = self.skill_registry.get_skill('notification')
        self.skill_registry.skills['toast'] = self.skill_registry.get_skill('notification')
        self.skill_registry.skills['video'] = self.skill_registry.get_skill('short_video_agent')
        self.skill_registry.skills['short'] = self.skill_registry.get_skill('short_video_agent')
        self.skill_registry.register_skill(CalendarSkill())
        self.skill_registry.register_skill(EmailSkill())

        # Custom Aliases

    async def process_request(self, user_input: str, on_event=None) -> str:
        placeholders = ["processing...", "executing", "thinking", "one moment", "working on it"]
        
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
        wisdom_block = "\n".join([f"- [{w['category'].upper()}]: {w['insight']}" for w in narrative_wisdom])
        
        allowed, reason = await self.governor.veto_check(user_input, model_router=self.model_router, wisdom=wisdom_block)
        if not allowed:
            viki_logger.warning(f"Governor Vetoed Request: {reason}")
            return f"I cannot comply. {reason}"

        # 4. Standard Safety Validation
        safe_input = self.safety.validate_request(user_input)
        
        # Reset interruption
        self.interrupt_signal.clear()
        self.signals.decay_signals()

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
        

        # URL Detection: If user shares a URL, auto-fetch content
        import re as _re
        urls = _re.findall(r'https?://[^\s<>"]+', safe_input)
        url_context = ""
        if urls:
            try:
                research_skill = self.skill_registry.get_skill('research')
                if research_skill:
                    for url in urls[:2]:  # Max 2 URLs
                        page_content = await research_skill.execute({'url': url})
                        url_context += f"\n{page_content}\n"
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

        # --- ORYTHIX DELIBERATION (v22) ---
        if on_event: on_event("status", "THINKING (Reflex)")
        
        # 1. Reflex Path (Habit Execution)
        reflex_resp, reflex_action = await self.reflex.think(user_input, model_router=self.model_router)
        if reflex_resp:
            self.scorecard.record_metric("reliability_rate", 1.0, context="reflex")
            self.memory.working.add_message("assistant", reflex_resp)
            return self._compress_output(reflex_resp)
        
        if reflex_action:
             # Fast Path Execution with Security Checks
             skill_name = reflex_action.skill_name
             params = reflex_action.parameters
             
             # 0. CAPABILITY CHECK (same as deliberation path)
             check_res = self.capabilities.check_permission(skill_name, params=params)
             if not check_res.allowed:
                 viki_logger.warning(f"Reflex action '{skill_name}' blocked: {check_res.reason}")
                 # Fall through to deliberation for safer handling
                 return await self.process_request(user_input, on_event=on_event)
             
             # 1. SAFETY VALIDATION
             if not self.safety.validate_action(skill_name, params):
                 viki_logger.warning(f"Reflex action '{skill_name}' failed safety check")
                 return "Safety Check: This reflex action is not permitted."
             
             # 2. SHADOW MODE GATE
             if self.shadow_mode:
                 viki_logger.info(f"Shadow Mode: Simulating reflex {skill_name}({params})")
                 return f"[Shadow Mode] Would execute reflex: {skill_name}({params})"
             
             # 3. EXECUTE
             skill = self.skill_registry.get_skill(skill_name)
             if skill:
                 try:
                     if on_event: on_event("status", f"EXECUTING (Reflex: {skill_name})")
                     result = await skill.execute(params)
                     self.memory.working.add_message("assistant", result)
                     return result
                 except Exception as e:
                     viki_logger.error(f"Reflex failed: {e}")
                     
                     # Report failure to reflex brain for blacklisting
                     self.reflex.report_failure(user_input)
                     
                     # Fall through to deliberation if reflex fails
        
        # 2. Deliberation Path (Foresight & Reasoning)
        if on_event: on_event("status", "DELIBERATING")
        
        # v23: Integrated Hierarchical Context Retrieval
        # Pass pre-fetched narrative_wisdom to avoid duplicate query
        memory_context = self.memory.get_full_context(safe_input, narrative_wisdom=narrative_wisdom)
        
        # Add relevant failures to context for error avoidance
        relevant_failures = self.learning.get_relevant_failures(safe_input, limit=3)
        memory_context['relevant_failures'] = relevant_failures
        
        world_understanding = self.world.get_understanding()
        
        # 3. Intelligence Governance (Judgment & Budget)
        # For v23, we use a simplified judgment for the high-level loop
        outcome = JudgmentOutcome.DEEP
        task_type = self._classify_task(safe_input) # vision, coding, reasoning, general
        use_lite = False # Use full reasoning by default for sovereignty
        
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
        
        for react_step in range(max_react_steps):
            step_label = f"[ReAct Step {react_step + 1}/{max_react_steps}]" if react_step > 0 else ""
            if step_label:
                viki_logger.info(f"{step_label} Continuing multi-step reasoning...")
                if on_event: on_event("status", f"THINKING {step_label}")
            
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
                                source="user_correction"
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
                return f"My deliberation layer encountered an error: {e}"

            # --- ACTION EXECUTION ---
            if viki_resp.action:
                skill_name = viki_resp.action.skill_name
                params = viki_resp.action.parameters
                
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
                
                # Safety Confirmation
                severity = self.safety.get_action_severity(skill_name, params)
                if severity in ["medium", "destructive"]:
                    self.pending_action = viki_resp.action
                    reply = (viki_resp.final_response or "").strip()
                    if not reply or reply.lower() in placeholders:
                        reply = "I understand. I have an action ready that needs your confirmation."
                    return f"{reply}\n\nSafety Check: This is a {severity} action. Confirm to proceed."

                # World Model Protection Zone Check
                if self.world.state.safety_zones.get(params.get('path', '')) == 'protected':
                    viki_logger.warning("Safety: Action targeting protected zone. Aborting.")
                    return "Safety Block: My world model flags this target as protected."

                # Shadow Mode Gate
                if self.shadow_mode:
                    viki_logger.info(f"Shadow Mode: Simulating {skill_name}({params})")
                    return f"[Shadow Mode] Would execute: {skill_name}({params}). Set shadow_mode: false to run for real."

                # Real Execution
                if on_event: on_event("status", f"EXECUTING {skill_name}")
                skill = self.skill_registry.get_skill(skill_name)
                if skill:
                    self.history.take_snapshot("ACTION_START", f"Executing {skill_name}", {"params": params})
                    
                    start_exec = time.time()
                    try:
                        result = await skill.execute(params)
                        latency = time.time() - start_exec
                        
                        # Record performance
                        selected_model = self.model_router.get_model(capabilities=[task_type])
                        selected_model.record_performance(latency, True)
                        self.skill_registry.record_execution(skill_name, True, latency)
                        
                        self.signals.update_signal("confidence", 0.05)
                        self.world.track_app_usage(skill_name)
                        
                        # Accumulate result for ReAct loop
                        action_results.append({
                            "action": f"{skill_name}({params})",
                            "result": str(result)[:1000],
                            "step": react_step + 1,
                        })
                        
                        if react_step < max_react_steps - 1:
                            continue
                        else:
                            self.last_interaction_time = time.time()
                            llm_response = viki_resp.final_response or "Directive sequence concluded."
                            all_results = "\n".join([f"Step {r['step']}: {r.get('result') or r.get('error')}" for r in action_results])
                            final_output = self._compress_output(f"{llm_response}\n\nExecution Logs:\n{all_results}")
                            break
                            
                    except Exception as e:
                        self.signals.update_signal("frustration", 0.3)
                        selected_model = self.model_router.get_model(capabilities=[task_type])
                        selected_model.record_performance(0.0, False)
                        self.skill_registry.record_execution(skill_name, False, 0.0)
                        self.learning.save_failure(skill_name, str(e), user_input)
                        return f"I must apologize. My attempt to execute '{skill_name}' failed: {e}."
                else:
                    viki_logger.warning(f"Skill '{skill_name}' not found.")
            
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
            break
        
        # --- ORYTHIX REFLECTION (v22) ---
        # --- ORYTHIX MEMORY REINFORCEMENT (v23) ---
        try:
             intent_summ = "General Interaction"
             confidence = 1.0
             if 'viki_resp' in locals() and viki_resp:
                  if viki_resp.final_thought:
                       intent_summ = viki_resp.final_thought.intent_summary
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
                    state = yaml.safe_load(f)
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
            return "question"
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
        fillers = [
            "I will now", "I am going to", "Let me see", "Starting the process of",
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
                facts = await self.learning.analyze_session(
                    session_trace=context,
                    session_outcome=summary,
                    model_router=self.model_router
                )
                viki_logger.info(f"Session analysis extracted {len(facts)} facts")
        except Exception as e:
            viki_logger.error(f"Narrative synthesis failed: {e}")

        self.wellness.stop()
        self.learning.prune_old_lessons()

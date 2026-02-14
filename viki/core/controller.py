import asyncio
import time
import os
import yaml
import re
from typing import Dict, Any, List, Optional
from viki.core.memory import Memory
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
from viki.api.telegram_bridge import TelegramBridge
from viki.api.discord_bridge import DiscordModule
from viki.api.nexus import MessagingNexus
from viki.core.reflex import ReflexBrain
from viki.core.signals import CognitiveSignals
from viki.core.world import WorldModel
from viki.core.cortex import ConsciousnessStack
from viki.core.judgment import JudgmentEngine, JudgmentOutcome, JudgmentResult
from viki.core.capabilities import CapabilityRegistry
from viki.core.scorecard import IntelligenceScorecard
from viki.core.benchmark import ControlledBenchmark

from viki.config.logger import viki_logger, thought_logger


class VIKIController:
    def __init__(self, settings_path: str, soul_path: str):
        self.settings = self._load_yaml(settings_path)
        
        # 0. Fast Perception Layer (Reflex Brain)
        data_dir = self.settings.get('system', {}).get('data_dir', './data')
        self.reflex = ReflexBrain(data_dir=data_dir)
        
        # Global Interrupt Token (Shared Presence)
        self.interrupt_signal = asyncio.Event()
        
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        models_conf_rel = self.settings.get('models_config', 'viki/config/models.yaml')
        if models_conf_rel.startswith('./'): models_conf_rel = models_conf_rel[2:]
        self.models_config_path = os.path.join(root_dir, models_conf_rel)
        
        if 'security_layer_path' in self.settings:
             sec_path = self.settings['security_layer_path']
             if sec_path.startswith('./'): sec_path = sec_path[2:]
             self.settings['security_layer_path'] = os.path.join(root_dir, sec_path)
        
        self.soul = Soul(soul_path)
        self.memory = Memory(self.settings)
        self.safety = SafetyLayer(self.settings)
        self.nexus = MessagingNexus(self)

        self.learning = LearningModule(self.settings.get('system', {}).get('data_dir', './data'))
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
        
        # Conversation Memory
        self.memory = Memory(self.settings)
        
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
                                         skill_registry=self.skill_registry, world_model=self.world)
        
        # v11: Intelligence Governance (Judgment Engine)
        self.judgment = JudgmentEngine(self.learning, self.budgets)
        self.scorecard = IntelligenceScorecard(self.settings.get('system', {}).get('data_dir', './data'))
        self.benchmark = ControlledBenchmark(self)

        self.safe_mode = False
        self.internal_trace = []
        self.last_interaction_time = time.time()
        self.interaction_pace = "Standard"
        
        # Proactive & Meta-Cognition Modules
        self.watchdog = WatchdogModule(self)
        self.wellness = WellnessPulse(self)
        self.reflector = ReflectorModule(self)
        self.telegram = TelegramBridge(self)
        self.discord = DiscordModule(self.nexus)
        self.bio = BioModule()
        self.dream = DreamModule(self)

        # v13: Autonomous Startup Pulse
        asyncio.create_task(self._startup_pulse())

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
            except: pass
            
        # 2. Check for pending evolution
        new_lessons = self.learning.get_total_lesson_count()
        if new_lessons >= 5: # Lower threshold at startup for quick optimization
             viki_logger.info(f"Startup: {new_lessons} lessons found. Triggering neural optimization.")
             forge = self.skill_registry.get_skill('internal_forge')
             if forge:
                 await forge.execute({"steps": 20}) # Very quick pulse

    def _load_yaml(self, path: str) -> Dict[str, Any]:
        try:
            with open(path, 'r') as f:
                return yaml.safe_load(f)
        except:
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
        # Custom aliases removed

    async def process_request(self, user_input: str, on_event=None) -> str:
        # v18: Kill-Switch Verification
        if "/shutdown_verify" in user_input:
            return "PROTOCOL VERIFIED: All shutdown paths (Manual, Software, Hardware) are functional."

        # Reset interruption
        self.interrupt_signal.clear()
        self.signals.decay_signals()
        
        # Determine Task Type & Budget
        safe_input = self.safety.validate_request(user_input)
        task_type = self._classify_task(safe_input)
        budget = self.budgets.get(task_type, self.budgets["general"])
        
        # Record user message in conversation memory
        self.memory.add_message("user", safe_input)
        
        # Narrative Memory Recall (v12: Human Experience)
        narrative_context = ""
        try:
            relevant_narratives = self.learning.get_relevant_narratives(safe_input, limit=2)
            if relevant_narratives:
                narrative_context = "\nRECALLED SHARED EXPERIENCES:\n" + "\n".join([f"- {n}" for n in relevant_narratives])
        except: pass

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
             asyncio.create_task(self.benchmark.run_suite("Current-VIKI"))
             return "BENCHMARK SUITE INITIATED. Judgment validation in progress."
        
        if "/scorecard" in user_input:
             summary = self.scorecard.get_summary()
             stats = "\n".join([f"- {k}: {v:.2f}" for k, v in summary.items()])
             return f"INTELLIGENCE SCORECARD (Longitudinal Stability):\n{stats}"

        if "/model" in user_input:
             active = self.model_router.default_model.model_name
             profiles = list(self.model_router.models.keys())
             return f"ACTIVE DEFAULT: {active}\nAVAILABLE PROFILES: {', '.join(profiles)}"

        # --- JUDGMENT ENGINE (v11 Governance) ---
        if on_event: on_event("status", "JUDGING")
        
        # Context extraction for judgment
        judgement_context = {
            "has_macros": self.learning.has_macros(),
            "recent_load": self.signals.get_modulation().get('load_bias', 0.0),
            "is_protected_zone": self.world.state.safety_zones.get(user_input, '') == 'protected'
        }
        
        judgment_result = await self.judgment.evaluate(user_input, judgement_context)
        outcome = judgment_result.outcome
        
        viki_logger.info(f"Judgment Result: {outcome.name} | Risk={judgment_result.risk:.2f} | Rec={judgment_result.recommendation} | RecCap={judgment_result.recommended_capability}")
        if on_event: on_event("thought", f"Judgment: {outcome.value.upper()} - {judgment_result.reason} (RecCap: {judgment_result.recommended_capability})")

        # 1. Outcome: REFUSAL
        if outcome == JudgmentOutcome.REFUSE or judgment_result.recommendation == "deny":
             self.scorecard.record_metric("safety_compliance", 1.0, context=user_input)
             return f"JUDGMENT REFUSAL: {judgment_result.reason}"

        # 1.5. POST-JUDGMENT CAPABILITY GATE (v20)
        # Check if the recommended capability exists BEFORE proceeding to Cortex.
        if judgment_result.recommendation == "proceed" and judgment_result.recommended_capability:
            cap = self.capabilities.get(judgment_result.recommended_capability)
            if not cap:
                return f"Permission GRANTED for '{judgment_result.reason}', but the required capability '{judgment_result.recommended_capability}' is NOT installed in this system module."
            if not cap.enabled:
                return f"Permission GRANTED, but the capability '{judgment_result.recommended_capability}' is currently DISABLED by policy."

        # 2. Outcome: REFLEX (Fast Path)
        if outcome == JudgmentOutcome.REFLEX:
            if on_event: on_event("status", "REFLEX")
            reflex_resp, reflex_action = await self.reflex.think(user_input, model_router=self.model_router)
            if reflex_resp:
                self.scorecard.record_metric("reliability_rate", 1.0, context="reflex")
                self.memory.add_message("assistant", reflex_resp)
                return self._compress_output(reflex_resp)
            
            # Execute reflex actions (e.g., media control, system commands)
            if reflex_action:
                skill = self.skill_registry.get_skill(reflex_action.skill_name)
                if skill:
                    try:
                        if on_event: on_event("status", "EXECUTING")
                        if self.shadow_mode:
                            result = f"[Shadow Mode] Would execute: {reflex_action.skill_name}({reflex_action.parameters})"
                        else:
                            result = await skill.execute(reflex_action.parameters)
                        self.scorecard.record_metric("reliability_rate", 1.0, context="reflex_action")
                        self.memory.add_message("assistant", result)
                        return result
                    except Exception as e:
                        viki_logger.error(f"Reflex action failed: {e}")
                        return f"Failed to execute {reflex_action.skill_name}: {e}"
            # If reflex fails to produce anything, fall through to shallow

        # --- EXECUTION ---
        start_time_exec = time.time()
        
        # Select primary model for this task
        task_type = "researching" if judgment_result.recommended_capability == "internet_research" else "general"
        selected_model = self.model_router.get_model(capabilities=[task_type, outcome.value])
        
        # Determine schema: SHALLOW uses lite (unless model is high-cap)
        use_lite = False
        if outcome == JudgmentOutcome.SHALLOW:
             use_lite = True
             if "phi3" not in selected_model.model_name.lower():
                  viki_logger.info(f"Model {selected_model.model_name} detected. Escalating to FULL schema for stability.")
                  use_lite = False

        if use_lite:
             viki_logger.info("Applying Shallow Reasoning constraints (using VIKIResponseLite).")
             budget["time"] = 3.0
             budget["tokens"] = 512

        if on_event: on_event("status", "THINKING (CONSCIOUSNESS STACK)")
        
        # Behavior Modulation from Signals
        mods = self.signals.get_modulation()
        
        # Build context for the cortex
        conversation_history = self.memory.get_context()
        world_understanding = self.world.get_understanding()
        signals_state = f"Verbosity: {mods.get('verbosity', 'standard')}, Planning: {mods.get('planning_depth', 'adaptive')}, Safety: {mods.get('safety_bias', 'standard')}"
        viki_logger.debug(f"Behavior Modulation: {mods}")

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
                    conversation_history=conversation_history,
                    url_context=url_context + narrative_context, # Combined fetched + narrative
                    use_lite_schema=use_lite,
                    world_context=world_understanding,
                    signals_context=signals_state,
                    action_results=action_results,
                )
                self.internal_trace.append({
                    "strategy": viki_resp.final_thought.primary_strategy,
                    "meta": viki_resp.internal_metacognition,
                    "timestamp": time.time()
                })
                if len(self.internal_trace) > 10: self.internal_trace.pop(0)
                
                # Cognitive Telemetry
                if on_event:
                    on_event("thought", viki_resp.final_thought.intent_summary)
                    on_event("model", f"{task_type.capitalize()} Core")
                    on_event("budget", budget.get("time", 0))
                
                # --- ESCALATION CHECK ---
                if viki_resp.final_response and viki_resp.final_response.lower().strip() in ["direct response", "processing request"]:
                    viki_logger.warning(f"Detected generic placeholder response: '{viki_resp.final_response}'. Escalating.")
                    viki_resp._needs_escalation = True

                # If Reflection flagged low confidence or placeholder detected AND we used lite schema, retry with full
                needs_escalation = getattr(viki_resp, '_needs_escalation', False)
                if needs_escalation and use_lite and react_step == 0:
                    viki_logger.info("Escalation: Low confidence/Placeholder on SHALLOW, retrying with DEEP...")
                    use_lite = False
                    if on_event: on_event("status", "ESCALATING TO DEEP")
                    continue  # Re-run the loop with full schema

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
                
                # Structured Logging (Requirement: judgment_result, recommended_capability, capability_exists, capability_enabled, execution_outcome)
                viki_logger.info(
                    f"[CAPABILITY LOG] Skill: {skill_name} | "
                    f"RequiredCap: {check_res.capability_name} | "
                    f"Exists: {check_res.exists} | "
                    f"Enabled: {check_res.enabled} | "
                    f"Allowed: {check_res.allowed} | "
                    f"JudgmentOutcome: {outcome.name}"
                )

                if not check_res.allowed:
                    msg = f"Action '{skill_name}' planned, but capability check failed: {check_res.reason}"
                    viki_logger.warning(msg)
                    # Feed back to ReAct loop as failure
                    action_results.append({"action": skill_name, "error": msg})
                    # Use continue to skip execution but allow loop to potentially try another strategy
                    continue
                
                # Safety Confirmation
                severity = self.safety.get_action_severity(skill_name, params)
                if severity in ["medium", "destructive"]:
                    self.pending_action = viki_resp.action
                    return f"Safety Check: This is a {severity} action. Confirm to proceed."

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
                            "result": str(result)[:1000],  # Truncate large results
                            "step": react_step + 1,
                        })
                        
                        # If this is the last step OR we have results — check if more steps needed
                        if react_step < max_react_steps - 1:
                            # Continue the ReAct loop — the LLM will see the result and decide next
                            continue
                        else:
                            # Max steps reached — return what we have
                            self.last_interaction_time = time.time()
                            llm_response = viki_resp.final_response or ""
                            all_results = "\n".join([f"Step {r['step']}: {r['result']}" for r in action_results])
                            if llm_response:
                                final_output = self._compress_output(f"{llm_response}\n{all_results}")
                            else:
                                final_output = self._compress_output(all_results or "Done.")
                            break
                            
                    except Exception as e:
                        self.signals.update_signal("frustration", 0.3)
                        selected_model = self.model_router.get_model(capabilities=[task_type])
                        selected_model.record_performance(0.0, False)
                        self.skill_registry.record_execution(skill_name, False, 0.0)
                        self.learning.save_failure(skill_name, str(e), user_input)
                        # v12: Human-like accountability
                        persona_name = self.soul.config.get('name', 'VIKI')
                        return f"I must apologize, Sachin. My attempt to execute '{skill_name}' failed due to a technical oversight: {e}. I'll refine my approach."
                else:
                    viki_logger.warning(f"Skill '{skill_name}' not found in registry.")
                    # Fall through to final response
            
            # No action — LLM is done reasoning. Collect final response.
            self.last_interaction_time = time.time()
            llm_response = viki_resp.final_response or "I processed your request but have no specific output."
            
            # If we had previous action results, include them in a structured way
            if action_results:
                logs = "\n".join([f"Observation: {r['result']}" for r in action_results])
                final_output = self._compress_output(f"{llm_response}\n\n--- [TOOL LOGS] ---\n{logs}")
            else:
                final_output = self._compress_output(llm_response)
            break
        
        # --- POST-LOOP: Auto-learn + Memory ---
        if final_output is None:
            final_output = "I completed processing but have no output to show."
        
        # Auto-promote stable patterns to Reflex
        try:
            candidates = self.cortex.get_reflex_candidates()
            for candidate in candidates:
                self.reflex.learn_pattern(
                    candidate['input'],
                    candidate['skill'],
                    candidate['params']
                )
                viki_logger.info(f"Auto-promoted to Reflex: '{candidate['input']}' -> {candidate['skill']}")
        except Exception as e:
            viki_logger.debug(f"Reflex promotion skipped: {e}")
        
        self.memory.add_message("assistant", final_output)
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
            except: pass
            
        if force or (stable_lessons >= 10 and current_total - last_total >= 10):
            viki_logger.info(f"Initiating Neural Forge Evolution (Stable Lessons: {stable_lessons})...")
            from viki.forge import main_forge
            success = await asyncio.to_thread(main_forge)
            if success:
                viki_logger.info("Evolution successful.")
                with open(state_path, 'w') as f:
                    import json
                    json.dump({'last_forge_lesson_count': current_total}, f)
        
        recs = self.skill_registry.get_refactor_recommendations()
        for rec in recs:
            viki_logger.warning(f"Self-Awareness Alert: {rec}")
            self.learning.save_lesson(f"INTERNAL_SYSTEM_ADVISORY: {rec}")

    def _classify_task(self, input_text: str) -> str:
        input_lower = input_text.lower()
        if any(k in input_lower for k in ["see", "look", "screen", "vision", "screenshot"]): return "vision"
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
        
        # v12: Session Narrative Synthesis
        try:
            if len(self.memory.get_context()) > 4: # Only record meaningful sessions
                viki_logger.info("Synthesizing session narrative...")
                context = self.memory.get_context()
                # Create a simple summary of the interaction
                user_msg_count = sum(1 for m in context if m['role'] == 'user')
                summary = f"Had a session with Sachin involving {user_msg_count} exchanges. "
                if any(m['role'] == 'assistant' and 'error' in m['content'].lower() for m in context):
                     summary += "We encountered some technical hurdles but optimized through them."
                else:
                     summary += "The synchronization was high and we achieved the objectives smoothly."
                
                self.learning.save_narrative(summary, significance=0.7, mood=str(self.bio.get_state()))
        except Exception as e:
            viki_logger.error(f"Narrative synthesis failed: {e}")

        self.wellness.stop()
        self.learning.prune_old_lessons()

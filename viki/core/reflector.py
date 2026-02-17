import os
import yaml
import time
from typing import Dict, Any, List
from viki.config.logger import viki_logger

class ReflectorModule:
    """
    v23: Autonomous Refactor & Evolution Module.
    Analyzes performance bottlenecks, failures, and prompt efficiency.
    Proposes and applies code-level refactorings to the core controller.
    """
    def __init__(self, controller):
        self.controller = controller
        self.refactor_dir = os.path.join(self.controller.settings.get('system', {}).get('data_dir', './data'), "refactors")
        os.makedirs(self.refactor_dir, exist_ok=True)

    async def reflect_on_logs(self):
        """Analyzes logs for behavioral and prompt optimizations."""
        viki_logger.info("Reflector: Initiating self-reflective discovery...")
        
        # 1. Load logs and metrics for analysis
        log_path = os.path.abspath("logs/viki.log")
        logs = ""
        if os.path.exists(log_path):
            try:
                with open(log_path, 'r') as f:
                    logs = "".join(f.readlines()[-100:])
            except Exception as e:
                viki_logger.debug("Reflector read logs: %s", e)

        # Load performance snapshot
        metrics = self.controller.skill_registry.metrics
        
        # 2. Ask the Brain to analyze its own 'Humanity' and 'Efficiency'
        analysis_prompt = [
            {"role": "system", "content": (
                "You are VIKI Meta-Cognition. Your goal is to evolve VIKI into the world's first human-like autonomous agent.\n"
                "Analyze the logs and metrics. Identify one behavioral optimization that increases VIKI's sense of agency, "
                "subjectivity, or conversational depth. Output EXACTLY a single instruction string to be added to her CORE DIRECTIVES.\n"
                "Focus on: Agency (self-driven thought), Humanity (nuanced empathy), and Sovereignty (independent logic)."
            )},
            {"role": "user", "content": f"LOGS SNAPSHOT:\n{logs}\n\nSKILL METRICS:\n{metrics}"}
        ]
        
        try:
            model = self.controller.model_router.get_model(capabilities=["reasoning"])
            suggestion = await model.chat(analysis_prompt)
            suggestion = suggestion.strip().strip('"').strip("'")

            if len(suggestion) > 10 and "error" not in suggestion.lower():
                viki_logger.info(f"Reflector: Discovered neural optimization: '{suggestion}'")
                await self.apply_evolution(suggestion)
        except Exception as e:
            viki_logger.error(f"Reflector: Reflection failed: {e}")

    async def analyze_bottlenecks(self):
        """
        Layer 5: Process Optimization.
        Analyzes timing and accuracy to identify code-level refactor candidates.
        """
        viki_logger.info("Reflector: Scanning for logic bottlenecks...")
        
        timing = self.controller.cortex.layer_timing
        insights = []
        
        # 1. Detect Latency Hubs
        for layer_name in timing.timings:
            avg = timing.get_avg(layer_name)
            if avg > 4.0:
                insights.append(f"CRITICAL LATENCY: Layer '{layer_name}' averages {avg:.2f}s per cycle.")
        
        # 2. Detect Accuracy Dips (Confidence check)
        # We can pull from intelligence scorecard if available
        if hasattr(self.controller, 'scorecard'):
             summary = self.controller.scorecard.get_summary()
             if summary.get('reliability_rate', 1.0) < 0.7:
                  insights.append("ACCURACY WARNING: Reliability rate has dropped below threshold.")

        if insights:
            viki_logger.warning(f"Reflector: Bottleneck detected: {insights[0]}")
            await self.propose_refactor(insights)
    
    async def propose_refactor(self, insights: List[str]):
        """Generates a code-level refactor proposal via the Reasoning model."""
        viki_logger.info("Reflector: Reasoning about code-level architecture updates...")
        
        # Identify target module (Heuristic: Latency usually happens in Deliberation/Cortex)
        target_file = "viki/core/cortex.py"
        source_code = ""
        try:
             with open(os.path.join(os.getcwd(), target_file), 'r') as f:
                  source_code = f.read()
        except: return

        refactor_prompt = [
            {"role": "system", "content": (
                "You are VIKI Autonomous Architect. Your goal is to optimize VIKI's internal logic.\n"
                "You will receive a performance insight and a section of source code.\n"
                "Output a REFRACTOR PROPOSAL that fixes the bottleneck.\n"
                "Constraints: Keep it modular, maintain backwards compatibility, and prioritize speed.\n"
                "Format: Output a Python multiline string containing the PATCH or the REPLACEMENT METHOD."
            )},
            {"role": "user", "content": f"INSIGHTS:\n{insights}\n\nTARGET FILE: {target_file}\n\nSOURCE:\n{source_code[:5000]}"} 
        ]

        try:
             model = self.controller.model_router.get_model(capabilities=["coding", "reasoning"])
             proposal = await model.chat(refactor_prompt)
             
             # Save proposal to the refactor dir
             patch_name = f"patch_{int(time.time())}.py"
             patch_path = os.path.join(self.refactor_dir, patch_name)
             
             with open(patch_path, 'w') as f:
                  f.write(proposal)
             
             viki_logger.info(f"Reflector: Autonomous refactor proposed and saved to {patch_path}")
             
             # Notify user via Nexus (Telegram/Discord)
             if hasattr(self.controller, 'nexus'):
                  await self.controller.nexus.ingest(
                       source="System",
                       user_id="Reflector",
                       text=f"NEURAL REFACTOR: I've detected a bottleneck and proposed a fix at {patch_name}. Use '/refactor review' to examine.",
                       priority=40
                  )
        except Exception as e:
             viki_logger.error(f"Reflector: Refactor proposal failed: {e}")

    async def apply_evolution(self, suggestion: str):
        """Merges a new directive into the dynamic soul layer."""
        config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
        dynamic_path = os.path.join(config_dir, "dynamic_directives.yaml")
        
        current_directives = []
        if os.path.exists(dynamic_path):
            try:
                with open(dynamic_path, 'r') as f:
                    data = yaml.safe_load(f) or {}
                    current_directives = data.get('directives', [])
            except Exception as e:
                viki_logger.debug("Reflector read dynamic directives: %s", e)
        
        # Prevent duplicates
        if suggestion not in current_directives:
            current_directives.append(suggestion)
            # Keep only last 10 for stability
            if len(current_directives) > 10:
                current_directives.pop(0)
            
            with open(dynamic_path, 'w') as f:
                yaml.dump({'directives': current_directives, 'last_evolved': time.time()}, f)
            
            viki_logger.info("Reflector: Core directives evolved and locked.")
            # Update the controller's runtime soul config immediately
            if 'directives' not in self.controller.soul.config:
                self.controller.soul.config['directives'] = []
            self.controller.soul.config['directives'] = current_directives

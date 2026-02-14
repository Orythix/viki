import os
import yaml
import time
from typing import Dict, Any, List
from viki.config.logger import viki_logger

class ReflectorModule:
    """
    Automated Prompt Engineering (APE) Module.
    Analyzes failures and suggests system prompt optimizations.
    """
    def __init__(self, controller):
        self.controller = controller

    async def reflect_on_logs(self):
        viki_logger.info("Reflector: Initiating self-reflective discovery...")
        
        # 1. Load logs and metrics for analysis
        log_path = os.path.abspath("logs/viki.log")
        logs = ""
        if os.path.exists(log_path):
            try:
                with open(log_path, 'r') as f:
                    logs = "".join(f.readlines()[-100:])
            except: pass

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
            except: pass
        
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

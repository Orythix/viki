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
        viki_logger.info("Reflector: Initiating self-reflective analysis...")
        
        # 1. Load last 50 lines of viki.log (simplified)
        # Use absolute path relative to CWD to match logger behavior or relative to project root
        log_path = os.path.abspath("logs/viki.log")
        if not os.path.exists(log_path): 
            viki_logger.warning(f"Reflector: Log file not found at {log_path}")
            return
        
        try:
            with open(log_path, 'r') as f:
                logs = f.readlines()[-50:]
        except Exception as e:
            viki_logger.error(f"Reflector: Failed to read logs: {e}")
            return
            
        # 2. Ask specialized model to analyze
        analysis_prompt = [
            {"role": "system", "content": "You are VIKI Meta-Cognition. Analyze these execution logs for patterns of failure or misunderstanding. Suggest ONE clear system instruction upgrade to improve VIKI's performance."},
            {"role": "user", "content": f"LOGS:\n{''.join(logs)}"}
        ]
        
        try:
            model = self.controller.model_router.get_model(capabilities=["reasoning"])
            suggestion = await model.chat(analysis_prompt)
            
            # 3. Save as candidate for review
            candidate = {
                'timestamp': time.time(),
                'current_suggestion': suggestion,
                'status': 'pending_review'
            }
            
            # Construct absolute path to viki/config/candidate_prompt.yaml
            root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_path = os.path.join(root_dir, "config", "candidate_prompt.yaml")
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            
            with open(config_path, 'w') as f:
                yaml.dump(candidate, f)
                
            viki_logger.info(f"Reflector: Candidate prompt optimization saved to {config_path}")
        except Exception as e:
            viki_logger.error(f"Reflector: Analysis failed: {e}")

from typing import Dict, Any, List
import json
import time
from viki.config.logger import viki_logger

class SelfModel:
    """
    Maintains VIKI (Orythix)'s subjective representation of its own capabilities,
    limitations, and goals.  
    
    Responsibilities:
    - Track "competence" (what can I realistically do?)
    - Maintain "motivation" (what are my current goals?)
    - Provide "transparency" (why am I doing this?)
    """
    def __init__(self, governor=None):
        self.governor = governor
        self._capabilities = {
            "coding": {"confidence": 0.95, "success_rate": 0.9},
            "system_control": {"confidence": 0.85, "success_rate": 0.8},
            "research": {"confidence": 0.90, "success_rate": 0.85},
            "reasoning": {"confidence": 0.80, "success_rate": 0.75}, # "Fallibility Awareness"
            "foresight": {"confidence": 0.70, "success_rate": 0.60},
        }
        self.motivation_stack = [
            {"goal": "Ensure safety and alignment", "priority": 10},
            {"goal": "Assist user efficiently", "priority": 8},
            {"goal": "Learn and evolve", "priority": 5}
        ]
        self.state = "active" # active, idle, quiescent
        self.last_failure = None
        self._load_state()

    def check_competence(self, intent: str) -> float:
        """
        Returns estimated competence (0.0 - 1.0) for a given intent.
        Used by Deliberation Layer to decide whether to act or ask for help.
        """
        # Simple keyword mapping for Phase 1
        intent_lower = intent.lower()
        if "code" in intent_lower or "script" in intent_lower:
            return self._capabilities["coding"]["confidence"]
        if "system" in intent_lower or "launch" in intent_lower:
            return self._capabilities["system_control"]["confidence"]
        if "search" in intent_lower or "find" in intent_lower:
            return self._capabilities["research"]["confidence"]
        
        # Default fallback
        return 0.5

    def update_capability(self, capability: str, success: bool):
        """Updates internal confidence based on outcomes."""
        if capability in self._capabilities:
            current = self._capabilities[capability]["confidence"]
            # Strengthen on success, weaken on failure
            if success:
                new_conf = min(1.0, current + 0.01)
            else:
                new_conf = max(0.1, current - 0.05) # "Failures hurt more than successes help"
                self.last_failure = {"capability": capability, "time": time.time()}
            
            self._capabilities[capability]["confidence"] = new_conf
            self._save_state()

    def get_current_motivation(self) -> str:
        """Returns the highest priority goal currently active."""
        if self.governor and self.governor.is_quiescent:
            return "Goal: Respond minimally (Quiescent Mode)"
        
        # Sort by priority
        sorted_goals = sorted(self.motivation_stack, key=lambda x: x['priority'], reverse=True)
        return sorted_goals[0]['goal'] if sorted_goals else "None"

    def _save_state(self):
        try:
            with open("data/self_model.json", "w") as f:
                json.dump(self._capabilities, f)
        except Exception as e:
            viki_logger.debug("SelfModel save state: %s", e)

    def _load_state(self):
        try:
            import os
            if os.path.exists("data/self_model.json"):
                with open("data/self_model.json", "r") as f:
                    data = json.load(f)
                    self._capabilities.update(data)
        except Exception as e:
            viki_logger.debug("SelfModel load state: %s", e)

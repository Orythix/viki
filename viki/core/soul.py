import yaml
from typing import Dict, Any, List

class Soul:
    def __init__(self, config_path: str):
        self.config = self._load_config(config_path)
        self.name = self.config.get('name', 'VIKI')
        self.directives = self.config.get('directives', [])
        self.tone = self.config.get('tone', {})

    def _load_config(self, path: str) -> Dict[str, Any]:
        try:
            with open(path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading SOUL config: {e}")
            return {}

    def get_system_prompt(self) -> str:
        """Generate the system prompt based on the SOUL configuration."""
        
        # Base Identity
        prompt = f"You are {self.name}\n{self.config.get('type')}\n\n"
        
        # Core Behavior
        behavior = self.config.get('behavior', [])
        if behavior:
            prompt += "CORE BEHAVIOR:\n" + "\n".join([f"- {b}" for b in behavior]) + "\n\n"

        # Decision & Planning
        decision = self.config.get('decision_intelligence', [])
        if decision:
            prompt += "DECISION AND PLANNING INTELLIGENCE:\n" + "\n".join([f"- {d}" for d in decision]) + "\n\n"
            
        # Skill Orchestration
        skills = self.config.get('skill_orchestration', [])
        if skills:
            prompt += "SKILL ORCHESTRATION:\n" + "\n".join([f"- {s}" for s in skills]) + "\n\n"

        # Model Routing
        routing = self.config.get('model_routing', [])
        if routing:
            prompt += "MODEL ROUTING:\n" + "\n".join([f"- {r}" for r in routing]) + "\n\n"

        # Confidence Scoring
        confidence = self.config.get('confidence_scoring', [])
        if confidence:
            prompt += "CONFIDENCE SCORING:\n" + "\n".join([f"- {c}" for c in confidence]) + "\n\n"

        # Memory & Learning
        memory = self.config.get('memory_learning', [])
        if memory:
            prompt += "MEMORY AND LEARNING:\n" + "\n".join([f"- {m}" for m in memory]) + "\n\n"

        # UI Awareness
        ui = self.config.get('ui_awareness', [])
        if ui:
            prompt += "UI AWARENESS:\n" + "\n".join([f"- {u}" for u in ui]) + "\n\n"

        # Safety & Control
        safety = self.config.get('safety', [])
        if safety:
            prompt += "SAFETY AND CONTROL:\n" + "\n".join([f"- {s}" for s in safety]) + "\n\n"

        # Output Discipline
        output = self.config.get('output_discipline', [])
        if output:
            prompt += "OUTPUT DISCIPLINE:\n" + "\n".join([f"- {o}" for o in output]) + "\n\n"
            
        return prompt

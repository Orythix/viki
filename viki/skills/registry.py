import importlib
import pkgutil
import inspect
import json
import os
import sys
import time
from typing import Dict, Any, Type, List
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger

class SkillRegistry:
    def __init__(self):
        self.skills: Dict[str, BaseSkill] = {}
        self.metrics: Dict[str, Dict[str, Any]] = {} # name -> {attempts, successes, failures, avg_latency}
        
        # Path for persistence
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_path = os.path.join(base_dir, "data", "skill_metrics.json")
        os.makedirs(os.path.dirname(self.data_path), exist_ok=True)
        self._load_metrics()

    def register_skill(self, skill: BaseSkill):
        """Register a new skill instance."""
        if skill.name in self.skills:
            viki_logger.warning(f"Overwriting existing skill '{skill.name}'")
        self.skills[skill.name] = skill
        viki_logger.info(f"Registered skill: {skill.name}")

    def get_skill(self, name: str) -> BaseSkill:
        """Retrieve a skill by name."""
        return self.skills.get(name)

    def list_skills(self) -> List[str]:
        """List all registered skill names."""
        return list(self.skills.keys())

    def record_execution(self, skill_name: str, success: bool, latency: float):
        """Update metrics for a skill execution."""
        if skill_name not in self.metrics:
            self.metrics[skill_name] = {"attempts": 0, "successes": 0, "failures": 0, "avg_latency": 0.0}
        
        m = self.metrics[skill_name]
        m["attempts"] += 1
        if success:
            m["successes"] += 1
        else:
            m["failures"] += 1
            
        # Running average for latency
        prev_avg = m["avg_latency"]
        n = m["attempts"]
        m["avg_latency"] = ((prev_avg * (n - 1)) + latency) / n
        
        self._save_metrics()

    def get_reliability_score(self, skill_name: str) -> str:
        """Return a formatted reliability string (e.g., '95% Success')."""
        if skill_name not in self.metrics:
            return "(Untested)"
        
        m = self.metrics[skill_name]
        if m["attempts"] == 0:
            return "(Untested)"
            
        rate = (m["successes"] / m["attempts"]) * 100
        latency = m["avg_latency"]
        
        status = ""
        if rate < 50: status = "UNSTABLE"
        elif rate > 90: status = "RELIABLE"
        
        return f"{rate:.0f}% Success ({latency:.2f}s) {status}"

    def get_context_description(self) -> str:
        """Generate formatted skill list with metrics for LLM context."""
        lines = ["TOOLS (with Performance Metrics):"]
        for name, skill in self.skills.items():
            metrics = self.get_reliability_score(name)
            lines.append(f"- {name}: {skill.description} [{metrics}]")
        return "\n".join(lines)

    def _load_metrics(self):
        if os.path.exists(self.data_path):
            try:
                with open(self.data_path, 'r') as f:
                    self.metrics = json.load(f)
            except Exception as e:
                viki_logger.error(f"Failed to load metrics: {e}")

    def _save_metrics(self):
        try:
            with open(self.data_path, 'w') as f:
                json.dump(self.metrics, f, indent=2)
        except Exception as e:
            viki_logger.error(f"Failed to save metrics: {e}")

    def get_refactor_recommendations(self) -> List[str]:
        """Identify skills that are chronically unstable and recommend refactors."""
        recommendations = []
        for name, m in self.metrics.items():
            if m["attempts"] > 5:
                rate = (m["successes"] / m["attempts"]) * 100
                if rate < 70:
                    recommendations.append(
                        f"Skill '{name}' is unstable ({rate:.0f}% success over {m['attempts']} tries). "
                        f"Consider simplifying its parameter schema or adding more robust error handling."
                    )
                elif m["avg_latency"] > 5.0:
                    recommendations.append(
                        f"Skill '{name}' is slow (avg {m['avg_latency']:.1f}s). "
                        "Consider refactoring to use asynchronous subprocesses or partial streaming."
                    )
        return recommendations

    def discover_skills(self, plugin_dir: str):
        """Dynamically load skills from a directory."""
        if not os.path.exists(plugin_dir):
            viki_logger.warning(f"Plugin directory not found: {plugin_dir}")
            return

        viki_logger.info(f"Discovering skills in {plugin_dir}...")
        
        sys.path.insert(0, plugin_dir)
        
        for filename in os.listdir(plugin_dir):
            if filename.endswith(".py") and not filename.startswith("__"):
                module_name = filename[:-3]
                try:
                    module = importlib.import_module(module_name)
                    
                    # Inspect for BaseSkill subclasses
                    for name, obj in inspect.getmembers(module):
                        if inspect.isclass(obj) and issubclass(obj, BaseSkill) and obj is not BaseSkill:
                            try:
                                skill_instance = obj()
                                self.register_skill(skill_instance)
                                viki_logger.info(f"Loaded plugin skill: {skill_instance.name}")
                            except Exception as e:
                                viki_logger.error(f"Failed to instantiate skill {name}: {e}")
                                
                except Exception as e:
                    viki_logger.error(f"Failed to load module {module_name}: {e}")
        
        # Clean up path
        sys.path.pop(0)

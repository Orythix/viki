import importlib
import pkgutil
import inspect
import json
import os
import sys
import time
import asyncio
from typing import Dict, Any, Type, List, Optional
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger

class SkillRegistry:
    def __init__(self):
        self.skills: Dict[str, BaseSkill] = {}
        self.metrics: Dict[str, Dict[str, Any]] = {} # name -> {attempts, successes, failures, avg_latency}
        
        # v26: Intent to Skill Mapping for Progressive Disclosure
        self.intent_map = {
            "media_control": ["media_control", "voice"],
            "system_command": ["system_control", "shell", "endpoint_guard"],
            "coding": ["dev_skill", "python_interpreter", "filesystem_skill", "coding_workflow", "manus", "lsp_tools"],
            "research": ["research", "summarize", "market_explorer", "pdf"],
            "security": ["security_tools", "autonomous_auditor", "mutation_pilot"],
            "governance": ["cache_pilot", "context_weaver", "mind_trace", "log_voyager"],
            "cloud": [],
            "devops": [],
            "system": [],
            "data": [],
            "ai": [],
            "productivity": [],
        }
        
        # Path for persistence
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_path = os.path.join(base_dir, "data", "skill_metrics.json")
        os.makedirs(os.path.dirname(self.data_path), exist_ok=True)
        self._load_metrics()

        # v25: Auto-discover dynamic skills on startup
        dynamic_dir = os.path.join(base_dir, "skills", "dynamic")
        if os.path.exists(dynamic_dir):
            self.discover_skills(dynamic_dir)

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

    def get_context_description(self, mode: str = "metadata", names: List[str] = None, skip_escalation: bool = False) -> str:
        """Generate formatted skill list for LLM context.
        
        Args:
            mode: 'metadata' (name+desc) or 'full' (schema+instructions)
            names: Optional list of skill names to include (if None, all are included)
            skip_escalation: If True, skip skills marked as escalation-only (playbooks, etc.)
        """
        escalation_skills = {"engineering_playbook", "megatron_lm_playbook", "coding_workflow"}
        
        if mode == "metadata":
            lines = ["TOOLS (Metadata Only):"]
            for name, skill in self.skills.items():
                if names and name not in names: continue
                if skip_escalation and name in escalation_skills: continue
                metrics = self.get_reliability_score(name)
                # Keep it very short (~100 tokens for all)
                lines.append(f"- {name}: {skill.description[:100]}... [{metrics}]")
            return "\n".join(lines)
        
        else: # Full mode
            lines = ["TOOL MANIFESTS (Full Specs):"]
            for name, skill in self.skills.items():
                if names and name not in names: continue
                if skip_escalation and name in escalation_skills: continue
                schema_json = json.dumps(skill.schema, indent=2)
                lines.append(f"## {name}\n{skill.description}\n\nINSTRUCTIONS:\n{skill.instructions}\n\nSCHEMA:\n{schema_json}\n")
            return "\n".join(lines)

    def get_relevant_skill_names(self, intent: str, user_input: str) -> List[str]:
        """Find skill names relevant to the current intent and input."""
        relevant = set(self.intent_map.get(intent, []))
        
        # Also check for direct name mentions in input
        input_lower = user_input.lower()
        for name in self.skills:
            if name in input_lower:
                relevant.add(name)
        
        return list(relevant)

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

    def load_sovereign_library(self, path: str, controller: Any):
        """Load 100+ skills from a JSON library and register them as BridgeSkills."""
        if not os.path.exists(path):
            viki_logger.warning(f"Sovereign Library not found at {path}")
            return

        try:
            with open(path, "r") as f:
                data = json.load(f)
            
            count = 0
            for category, skills in data.items():
                for spec in skills:
                    name = spec["name"]
                    desc = spec["description"]
                    cmd = spec["command"]
                    
                    # Register as a BridgeSkill
                    skill = LibrarySkillBridge(name, desc, cmd, controller)
                    self.register_skill(skill)
                    
                    # Also update intent map
                    if category in self.intent_map:
                        self.intent_map[category].append(name)
                    else:
                        self.intent_map.setdefault("general", []).append(name)
                    
                    count += 1
            
            viki_logger.info(f"Sovereign Tool Hub: Successfully loaded {count} skills.")
        except Exception as e:
            viki_logger.error(f"Failed to load Sovereign Library: {e}")

class LibrarySkillBridge(BaseSkill):
    """A generic skill that executes a predefined command template."""
    def __init__(self, name: str, description: str, command_template: str, controller: Any):
        super().__init__()
        self._name = name
        self._description = description
        self._command_template = command_template
        self._controller = controller

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def schema(self) -> Dict[str, Any]:
        # Extract variables from template like {path}
        import re
        vars = re.findall(r'\{(\w+)\}', self._command_template)
        properties = {}
        for v in vars:
            properties[v] = {"type": "string", "description": f"Value for {v}"}
        
        return {
            "type": "object",
            "properties": properties,
            "required": vars
        }

    async def execute(self, params: Dict[str, Any]) -> str:
        try:
            # Format command
            cmd = self._command_template.format(**params)
            
            # Execute via shell skill or controller's sandbox
            shell = self._controller.skill_registry.get_skill("shell")
            if shell:
                return await shell.execute({"command": cmd})
            
            # Fallback to subprocess if shell skill not available
            import subprocess
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            return proc.stdout or proc.stderr or "Success (No Output)"
        except Exception as e:
            return f"Error executing {self._name}: {e}"

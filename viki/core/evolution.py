import os
import json
import time
import ast
from typing import List, Dict, Any, Optional
from viki.config.logger import viki_logger

class EvolutionEngine:
    """
    Adaptive Self-Modification Engine (v25)
    Gradual, auditable self-improvement through user-approved modifications.
    
    Supports:
    - New reflex shortcuts (Pattern promotion)
    - Adjusted confidence thresholds (Layer logic)
    - Tweaked priority weightings (Subjective Agency)
    """
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.state_file = os.path.join(data_dir, "viki_evolution_mutations.json")
        self.mutations = self._load_mutations()
        self.reflex = None # Set by controller
        self.model_router = None # Set by controller
        self.skill_registry = None # Set by controller
        self.crystallized_summary = self.mutations.get("crystallized_summary", "")
        self.dynamic_skills_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills", "dynamic")
        os.makedirs(self.dynamic_skills_dir, exist_ok=True)
        
    def set_reflex_module(self, reflex):
        self.reflex = reflex

    def set_model_router(self, router):
        self.model_router = router

    def set_skill_registry(self, registry):
        self.skill_registry = registry
        
    def _load_mutations(self) -> Dict[str, Any]:
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                viki_logger.warning(f"Failed to load mutations from {self.state_file}: {e}")
        return {
            "applied": [], # List of applied mutations
            "pending": [], # List of proposed mutations waiting for approval or success streak
            "history": []  # List of all past mutations
        }

    def _save_mutations(self):
        os.makedirs(self.data_dir, exist_ok=True)
        self.mutations["crystallized_summary"] = self.crystallized_summary
        with open(self.state_file, 'w') as f:
            json.dump(self.mutations, f, indent=4)

    def propose_mutation(self, m_type: str, description: str, value: Any, pattern_id: str = None):
        """Propose a new mutation based on a detected pattern."""
        # Check if already proposed or applied
        for m in self.mutations["applied"] + self.mutations["pending"]:
            if m["description"] == description:
                return None

        proposal = {
            "id": f"mut_{int(time.time())}",
            "type": m_type, # reflex, confidence, priority
            "description": description,
            "value": value,
            "pattern_id": pattern_id,
            "created_at": time.time(),
            "status": "pending",
            "success_count": 0
        }
        
        self.mutations["pending"].append(proposal)
        self._save_mutations()
        viki_logger.info(f"Evolution: New mutation proposed: {description}")
        return proposal

    def get_pending_proposals(self) -> List[Dict[str, Any]]:
        return self.mutations["pending"]

    def approve_mutation(self, m_id: str) -> bool:
        for i, m in enumerate(self.mutations["pending"]):
            if m["id"] == m_id:
                # Type-specific application
                if m["type"] == "reflex" and self.reflex:
                    val = m["value"]
                    self.reflex.learn_pattern(val["input"], val["skill"], val["params"])
                
                if m["type"] == "skill_synthesis":
                    self._apply_skill_mutation(m)

                m["status"] = "applied"
                m["applied_at"] = time.time()
                self.mutations["applied"].append(self.mutations["pending"].pop(i))
                self._save_mutations()
                viki_logger.info(f"Evolution: Approved mutation {m_id} applied.")
                return True
        return False

    def reject_mutation(self, m_id: str) -> bool:
        for i, m in enumerate(self.mutations["pending"]):
            if m["id"] == m_id:
                m["status"] = "rejected"
                m["rejected_at"] = time.time()
                self.mutations["history"].append(self.mutations["pending"].pop(i))
                self._save_mutations()
                return True
        return False

    def record_success(self, pattern_id: str):
        """Increment success count for pending mutations related to a pattern."""
        mutations_to_apply = []
        for m in self.mutations["pending"]:
            if m.get("pattern_id") == pattern_id:
                m["success_count"] += 1
                if m["success_count"] >= 3:
                    mutations_to_apply.append(m["id"])
                    viki_logger.info(f"Evolution: Mutation {m['id']} auto-applying after 3 consistent successes.")
        
        for m_id in mutations_to_apply:
            self.approve_mutation(m_id)
            
        if mutations_to_apply:
            self._save_mutations()

    def get_active_mutations(self, m_type: str = None) -> List[Dict[str, Any]]:
        if m_type:
            return [m for m in self.mutations["applied"] if m["type"] == m_type]
        return self.mutations["applied"]

    def get_agent_weightings(self) -> Dict[str, float]:
        """Synthesize final weightings for the Deliberation Layer."""
        weights = {
            "curiosity": 1.0,
            "skepticism": 1.0,
            "efficiency": 1.0,
            "autonomy": 1.0
        }
        for m in self.get_active_mutations("priority"):
            val = m.get("value", {})
            for k, v in val.items():
                if k in weights:
                    weights[k] += v
        return weights

    def get_evolution_summary(self, limit: int = 10) -> str:
        """
        v25: Returns a human-readable summary of identity shifts.
        Prioritizes crystallized summary if log is long.
        """
        applied = self.mutations.get("applied", [])
        
        summary = "IDENTITY EVOLUTION LOG:\n"
        if self.crystallized_summary:
            summary += f"[CRYSTALLIZED IDENTITY]: {self.crystallized_summary}\n"

        if not applied:
            if not self.crystallized_summary:
                return "Identity Status: Stable. No significant deviations from core priors recorded."
            return summary
        
        # Only show the most recent mutations that haven't been crystallized yet
        # (Assuming they are added after the last crystallization)
        recent = applied[-limit:]
        reflex_count = len([m for m in recent if m['type'] == 'reflex'])
        priority_shifts = [m for m in recent if m['type'] == 'priority']
        
        summary += f"RECENT SHIFTS (Last {len(recent)} interactions):\n"
        if reflex_count:
            summary += f"- Compiled {reflex_count} new reflex shortcuts for habituated tasks.\n"
        
        for ps in priority_shifts:
            summary += f"- {ps.get('description', 'Weighting adjustment')}\n"
            
        return summary

    async def crystallize_identity(self):
        """Periodically consolidate the mutation history into a single narrative thread."""
        if not self.model_router or not self.mutations["applied"]:
            return

        viki_logger.info("Evolution: Crystallizing mental identity...")
        
        applied = self.mutations["applied"]
        history_text = "\n".join([f"- {m['description']} (at {m.get('applied_at', 0)})" for m in applied])
        
        prompt = [
            {"role": "system", "content": (
                "You are VIKI Meta-Cognitive Archivist. Your goal is to simplify a complex log of behavioral mutations "
                "into a single, high-level narrative summary of WHO VIKI is becoming.\n"
                "Constraints: Max 3 sentences. Focus on trajectory, preferences, and agency."
            )},
            {"role": "user", "content": f"CURRENT IDENTITY BASE: {self.crystallized_summary}\n\nNEW MUTATIONS:\n{history_text}"}
        ]
        
        try:
            model = self.model_router.get_model(capabilities=["reasoning"])
            new_summary = await model.chat(prompt)
            self.crystallized_summary = new_summary.strip()
            # Archive applied to history to keep 'applied' recent
            self.mutations["history"].extend(self.mutations["applied"])
            self.mutations["applied"] = []
            self._save_mutations()
            viki_logger.info("Evolution: Identity crystallized and log archived.")
        except Exception as e:
            viki_logger.error(f"Evolution: Crystallization failed: {e}")

    async def propose_skill(self, task_description: str, code_hint: str = ""):
        """v25: Neural Forge v2 - Synthesize a new code-based skill."""
        if not self.model_router:
            return None

        viki_logger.info(f"Evolution: Forging new skill for: {task_description}")
        
        prompt = [
            {"role": "system", "content": (
                "You are the VIKI Neural Forge. Your goal is to write a high-quality Python skill for the VIKI framework.\n"
                "The skill must inherit from `BaseSkill` which must be imported as `from viki.skills.base import BaseSkill`. \n"
                "Structure:\n"
                "- name: Short unique string (snake_case)\n"
                "- description: What it does\n"
                "- schema: Dict for input parameters\n"
                "- execute: Async method that returns a string result.\n\n"
                "Ensure ALL necessary imports are included (e.g., `import sys`, `import json`, `from viki.skills.base import BaseSkill`).\n"
                "Output ONLY the code in a markdown block."
            )},
            {"role": "user", "content": f"TASK: {task_description}\nHINT: {code_hint}"}
        ]
        
        try:
            model = self.model_router.get_model(capabilities=["coding", "reasoning"])
            code_resp = await model.chat(prompt)
            # Extract code from markdown block
            import re
            code_match = re.search(r"```python\n(.*?)```", code_resp, re.DOTALL)
            code = code_match.group(1) if code_match else code_resp
            
            # Extract name for ID
            name_match = re.search(r"@property.*?def name\(self\).*?return \"(.*?)\"", code, re.DOTALL)
            skill_name = name_match.group(1) if name_match else f"skill_{int(time.time())}"
            
            mutation = self.propose_mutation(
                m_type="skill_synthesis",
                description=f"Neural Forge: New skill '{skill_name}' for {task_description}",
                value={"code": code, "skill_name": skill_name}
            )
            return mutation
        except Exception as e:
            viki_logger.error(f"Evolution: Skill synthesis failed: {e}")
            return None

    def _validate_skill_code(self, code: str) -> tuple[bool, str]:
        """Validate dynamically generated skill code for security issues."""
        try:
            # Parse the code into an AST
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"Syntax error in generated code: {e}"
        
        # Dangerous patterns to detect
        dangerous_imports = {'os.system', 'subprocess', 'eval', 'exec', '__import__', 'compile'}
        dangerous_calls = {'eval', 'exec', 'compile', '__import__'}
        
        for node in ast.walk(tree):
            # Check for dangerous imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if any(danger in alias.name for danger in ['subprocess', 'os.system']):
                        return False, f"Dangerous import detected: {alias.name}"
            
            if isinstance(node, ast.ImportFrom):
                if node.module and any(danger in node.module for danger in ['subprocess', 'os']):
                    for alias in node.names:
                        if alias.name in ['system', 'popen', 'spawn']:
                            return False, f"Dangerous import detected: from {node.module} import {alias.name}"
            
            # Check for dangerous function calls
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in dangerous_calls:
                    return False, f"Dangerous function call detected: {node.func.id}()"
        
        # Verify BaseSkill inheritance
        has_base_skill = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    if isinstance(base, ast.Name) and base.id == 'BaseSkill':
                        has_base_skill = True
                        break
        
        if not has_base_skill:
            return False, "Generated code does not inherit from BaseSkill"
        
        return True, "Code validation passed"
    
    def _apply_skill_mutation(self, mutation: Dict[str, Any]):
        """Writes and registers a synthesized skill after security validation."""
        val = mutation["value"]
        code = val["code"]
        skill_name = val["skill_name"]
        
        # Security validation
        is_valid, validation_msg = self._validate_skill_code(code)
        if not is_valid:
            viki_logger.error(f"Evolution: Skill mutation rejected - {validation_msg}")
            viki_logger.error(f"Rejected code:\n{code[:500]}")
            return
        
        viki_logger.info(f"Evolution: Skill code validated successfully - {validation_msg}")
        
        file_path = os.path.join(self.dynamic_skills_dir, f"{skill_name}.py")
        try:
            with open(file_path, 'w') as f:
                f.write(code)
            viki_logger.info(f"Evolution: Skill code written to {file_path}")
            
            # Log full audit trail
            viki_logger.info(f"Evolution Audit: Skill '{skill_name}' created at {time.time()}")
            viki_logger.debug(f"Evolution Audit: Code preview:\n{code[:200]}...")
            
            if self.skill_registry:
                # Hot-load the new module
                self.skill_registry.discover_skills(self.dynamic_skills_dir)
                viki_logger.info(f"Evolution: Skill '{skill_name}' hot-loaded into registry.")
        except Exception as e:
            viki_logger.error(f"Evolution: Failed to apply skill mutation: {e}")

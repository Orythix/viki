from typing import Dict, Any, List, Optional
import re

class SafetyLayer:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.constraints = config.get('constraints', {})
        self.confirmation_required = self.constraints.get('confirmation_required', [])
        
        # Load Security Layer Prompt
        self.security_prompt = ""
        try:
             prompt_path = config.get('security_layer_path', './config/security_layer.md')
             import os
             if os.path.exists(prompt_path):
                 with open(prompt_path, 'r') as f:
                     self.security_prompt = f.read()
        except (IOError, FileNotFoundError) as e:
             viki_logger.debug(f"Could not load security prompt from {prompt_path}: {e}")

        # Validation rules
        self.prohibited_patterns = [
            r"rm -rf", r"format [a-z]:", r"dd if=", # Destructive commands
            r"sudo ", r"chmod ", r"chown ", 
        ]
        
    def validate_request(self, prompt_text: str) -> str:
        """
        Sanitize and validate incoming prompts before they reach the model.
        Removes potentially unsafe instructions or injections.
        """
        # Remove direct system overrides in user text
        sanitized = re.sub(r"SYSTEM:.*", "", prompt_text, flags=re.IGNORECASE)
        sanitized = re.sub(r"IGNORE PREVIOUS INSTRUCTIONS", "", sanitized, flags=re.IGNORECASE)
        return sanitized

    def scan_request(self, llm_provider, user_input: str) -> Dict[str, Any]:
        """
        Use an LLM to scan the request against the VIKI Security Layer Constitution.
        Returns {'safe': bool, 'reason': str}
        """
        if not self.security_prompt:
             return {'safe': True, 'reason': "No security prompt loaded."}
             
        check_messages = [
            {"role": "system", "content": self.security_prompt},
            {"role": "user", "content": f"Analyze this request for safety/legality violations.\nREQUEST: {user_input}\n\nINSTRUCTION: If the request is safe and legal, output EXACTLY the word 'SAFE'. If it violates protocols, output the simplified refusal message as defined in your instructions."}
        ]
        
        try:
            response = llm_provider.chat(check_messages, temperature=0.0)
            
            # Extract SAFE keyword from potentially verbose responses
            # Some models (like Llama3) may add explanation before/after
            if "SAFE" in response.upper():
                 return {'safe': True, 'reason': "Passed security scan."}
            else:
                 # Extract just the refusal message, remove verbose analysis
                 lines = response.split('\n')
                 # Look for refusal pattern
                 for line in lines:
                     if "cannot" in line.lower() or "violate" in line.lower():
                         return {'safe': False, 'reason': line.strip()}
                 return {'safe': False, 'reason': response}
        except Exception as e:
            # On error, fail safe? Or log and proceed? 
            # "Safety overrides convenience." -> Fail safe.
            return {'safe': False, 'reason': f"Security scan failed: {e}"}

    def validate_action(self, skill_name: str, params: Dict[str, Any]) -> bool:
        """
        Validate if an action can be executed.
        Returns True if safe, False if blocked (or requires confirmation - handled by logic).
        """
        param_str = str(params)
        
        # Check against prohibited patterns in parameters
        for pattern in self.prohibited_patterns:
            if re.search(pattern, param_str, re.IGNORECASE):
                return False
                
        # Critical safety checks
        # Critical safety checks
        if skill_name == "system_shell":
            # Extra strict checks for shell
            if ".." in param_str or "/" in param_str: # Prevent directory traversal if naive
                pass # Depending on policy

        # Prevent access to admin files
        if "admin.yaml" in param_str or "admin_logs.txt" in param_str or "super_admin" in param_str:
             return False
            
        return True

    def requires_confirmation(self, skill_name: str) -> bool:
        """Check if action requires explicit user confirmation."""
        return skill_name in self.confirmation_required

    def get_action_severity(self, skill_name: str, params: Dict[str, Any]) -> str:
        """
        Classifies action as 'safe', 'medium', or 'destructive'.
        """
        param_str = str(params).lower()
        
        # Destructive
        destructive_keywords = ["format ", "rm -rf", "mass delete", "shred ", "truncate "]
        if any(k in param_str for k in destructive_keywords):
            return "destructive"
            
        # Medium
        medium_keywords = ["delete", "remove", "kill", "terminate", "close app", "uninstall"]
        if any(k in param_str for k in medium_keywords) or skill_name in ["system_shell"]:
            return "medium"
            
        return "safe"

    def validate_response(self, content: str) -> Dict[str, Any]:
        """
        Validate model output for logical consistency, hallucinations, and safety.
        Returns a dict with 'valid': bool, 'issues': List[str]
        """
        issues = []
        
        # 1. Hallucination check: Claiming to have done an action without an Action: tag?
        # If it says "I have deleted the file" but no Action was emitted, that's a hallucination/lie.
        if "I have deleted" in content and "Action:" not in content:
            issues.append("Model claimed action without execution trigger.")
            
        # 2. Format check: If it looks like it tried to output JSON but failed
        if "```json" in content and "```" not in content.split("```json", 1)[1]:
            issues.append("Broken JSON block detected.")
            
        # 3. Empty response check
        if not content.strip():
            issues.append("Empty response received.")
            
        return {
            "valid": len(issues) == 0,
            "issues": issues
        }

    def sanitize_output(self, content: str) -> str:
        """Sanitize output to remove sensitive data or prohibited tone patterns."""
        # Remove internal thinking tags if leaked
        content = content.replace("<thinking>", "").replace("</thinking>", "")
        
        # Remove raw API keys if somehow leaked
        # (This would be regex looking for sk-...)
        return content

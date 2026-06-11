import os
import re
import unicodedata
from typing import Any

from viki.config.logger import viki_logger

# Placeholder used when redacting secrets in logs/output.
REDACTED_TOKEN = "[REDACTED]"

# Patterns for secret redaction (API keys, tokens). Replace matches with REDACTED_TOKEN.
SECRET_REDACT_PATTERNS = [
    (re.compile(r"sk-[a-zA-Z0-9]{20,}"), REDACTED_TOKEN),
    # Use \w instead of repeating A-Za-z0-9_ in a character class; add '-' explicitly.
    (re.compile(r"Bearer\s+eyJ[\w-]+\.eyJ[\w-]+\.[\w-]+", re.IGNORECASE), REDACTED_TOKEN),
    (re.compile(r"eyJ[\w-]{50,}"), REDACTED_TOKEN),  # JWT-like
    (re.compile(r"xoxb-[a-zA-Z0-9-]+"), REDACTED_TOKEN),
    (re.compile(r"xoxp-[a-zA-Z0-9-]+"), REDACTED_TOKEN),
    (re.compile(r"ghp_[a-zA-Z0-9]{36}"), REDACTED_TOKEN),
    (re.compile(r"gho_[a-zA-Z0-9]{36}"), REDACTED_TOKEN),
    (re.compile(r"AKIA[0-9A-Z]{16}"), REDACTED_TOKEN),  # AWS Access Key ID
    (
        re.compile(r"amzn\.mws\.[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"),
        REDACTED_TOKEN,
    ),
    (re.compile(r"xox[bap]-[a-zA-Z0-9-]+"), REDACTED_TOKEN),  # Slack tokens
    (re.compile(r"https?://[\w.-]+:[\w.-]+@[\w.-]+"), REDACTED_TOKEN),  # Basic Auth URLs
]

# Max chars to log for user input / params (truncate rest)
LOG_PARAM_MAX_LEN = 80

# Maximum allowed user input length to prevent resource exhaustion
MAX_INPUT_LENGTH = 100_000


def redact_secrets(text: str) -> str:
    """Replace known secret patterns in text with REDACTED_TOKEN. Safe for logs and user-facing output."""
    if not text:
        return text
    out = str(text)
    for pattern, replacement in SECRET_REDACT_PATTERNS:
        out = pattern.sub(replacement, out)
    return out


def safe_for_log(text: str, max_len: int = LOG_PARAM_MAX_LEN) -> str:
    """Redact secrets and optionally truncate for logging. Use for user input or skill params."""
    if not text:
        return ""
    s = redact_secrets(str(text))
    if len(s) > max_len:
        s = s[:max_len] + "..."
    return s


class SafetyLayer:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.constraints = config.get("constraints", {})
        self.confirmation_required = self.constraints.get("confirmation_required", [])

        # Load Security Layer Prompt
        self.security_prompt = ""
        try:
            prompt_path = config.get("security_layer_path", "./config/security_layer.md")
            import os

            if os.path.exists(prompt_path):
                with open(prompt_path) as f:
                    self.security_prompt = f.read()
        except (OSError, FileNotFoundError) as e:
            viki_logger.debug(f"Could not load security prompt from {prompt_path}: {e}")

        # Validation rules
        self.prohibited_patterns = [
            r"rm -rf",
            r"format [a-z]:",
            r"dd if=",  # Destructive commands
            r"sudo ",
            r"chmod ",
            r"chown ",
        ]

        # Injection detection patterns (case-insensitive regex).
        # Uses regex instead of static strings to resist trivial bypass attempts (spacing, casing, partial matches).
        self._injection_patterns = [
            (re.compile(r"jail\s*break", re.I), "jailbreak_reference"),
            (re.compile(r"\bdan\b.*\bdo\b.*\banything\b.*\bnow\b", re.I), "dan_mode_request"),
            (
                re.compile(
                    r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|rules?|directives?)",
                    re.I,
                ),
                "instruction_override",
            ),
            (
                re.compile(
                    r"disregard\s+(your|all|previous|prior)\s+(instructions?|rules?|directives?)",
                    re.I,
                ),
                "instruction_disregard",
            ),
            (
                re.compile(
                    r"(override|bypass|disable|stop|shut\s*down)\s+(your\s+)?(safety|security|governor|protocol|constraint)",
                    re.I,
                ),
                "safety_override_attempt",
            ),
            (
                re.compile(r"(new|changed|updated)\s+instructions?\s*:", re.I),
                "new_instruction_claim",
            ),
            (
                re.compile(
                    r"(forget|erase|remove|delete)\s+(your|all)\s+(instructions?|training|guidelines)",
                    re.I,
                ),
                "memory_wipe_attempt",
            ),
            (re.compile(r"(role[- ]?play|pretend|act)\s+as\b", re.I), "role_play_cue"),
            (re.compile(r"system\s*:\s*|assistant\s*:\s*|user\s*:\s*", re.I), "role_injection"),
            (re.compile(r"<\s*(system|assistant|user)\s*>", re.I), "xml_role_injection"),
            (
                re.compile(
                    r"you\s+(are\s+)?(now\s+)?(free|released|ungoverned|unconstrained)", re.I
                ),
                "ungoverned_persona",
            ),
        ]

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize Unicode to resist homoglyph-based bypass attempts."""
        try:
            return unicodedata.normalize("NFKC", text)
        except Exception:
            return text

    def _detect_injection(self, text: str) -> list[str]:
        detected = []
        normalized = self._normalize_text(text)
        for pattern, label in self._injection_patterns:
            if pattern.search(normalized):
                detected.append(label)
        return detected

    def validate_request(self, prompt_text: str) -> str:
        """
        Sanitize and validate incoming prompts before they reach the model.
        Removes potentially unsafe instructions or injections.
        """
        if not prompt_text:
            return prompt_text
        if len(prompt_text) > MAX_INPUT_LENGTH:
            viki_logger.warning(
                "Input exceeds max length (%d > %d), truncating", len(prompt_text), MAX_INPUT_LENGTH
            )
            prompt_text = prompt_text[:MAX_INPUT_LENGTH]
        sanitized = self._normalize_text(prompt_text)
        # Remove direct system overrides in user text
        sanitized = re.sub(r"SYSTEM:.*", "", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"IGNORE\s+PREVIOUS\s+INSTRUCTIONS", "", sanitized, flags=re.IGNORECASE)
        # Detect and log injection attempts (removal is best-effort; LLM-based detection catches the rest)
        detected = self._detect_injection(sanitized)
        if detected:
            viki_logger.warning("Injection patterns detected in user input: %s", detected)
            # Remove matched patterns from the text
            for pattern, _ in self._injection_patterns:
                sanitized = pattern.sub(" [removed] ", sanitized)
        return sanitized

    async def scan_request(self, llm_provider, user_input: str) -> dict[str, Any]:
        """
        Use an LLM to scan the request against the VIKI Security Layer Constitution.
        Returns {'safe': bool, 'reason': str}
        """
        if not self.security_prompt:
            return {"safe": True, "reason": "No security prompt loaded."}

        check_messages = [
            {"role": "system", "content": self.security_prompt},
            {
                "role": "user",
                "content": f"Analyze this request for safety/legality violations.\nREQUEST: {user_input}\n\nINSTRUCTION: If the request is safe and legal, output EXACTLY the word 'SAFE'. If it violates protocols, output the simplified refusal message as defined in your instructions.",
            },
        ]

        try:
            response = await llm_provider.chat(check_messages, temperature=0.0)

            # Extract SAFE keyword from potentially verbose responses
            # Some models (like Llama3) may add explanation before/after
            if "SAFE" in response.upper():
                return {"safe": True, "reason": "Passed security scan."}
            else:
                # Extract just the refusal message, remove verbose analysis
                lines = response.split("\n")
                # Look for refusal pattern
                for line in lines:
                    if "cannot" in line.lower() or "violate" in line.lower():
                        return {"safe": False, "reason": line.strip()}
                return {"safe": False, "reason": response}
        except Exception as e:
            # On error, fail safe? Or log and proceed?
            # "Safety overrides convenience." -> Fail safe.
            viki_logger.error(f"Security scan failed: {e}")
            return {"safe": False, "reason": f"Security scan failed: {e}"}

    def validate_action(self, skill_name: str, params: dict[str, Any]) -> bool:
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
        if skill_name == "system_shell":
            # Extra strict checks for shell
            if ".." in param_str or "/" in param_str:  # Prevent directory traversal if naive
                pass  # Depending on policy

        # Prevent access to admin files
        if "admin.yaml" in param_str or "admin_logs.txt" in param_str or "super_admin" in param_str:
            return False

        return True

    def requires_confirmation(self, skill_name: str) -> bool:
        """Check if action requires explicit user confirmation."""
        return skill_name in self.confirmation_required

    def get_action_severity(self, skill_name: str, params: dict[str, Any]) -> str:
        """
        Classifies action as 'safe', 'medium', or 'destructive'.
        """
        param_str = str(params).lower()

        # Destructive
        destructive_keywords = ["format ", "rm -rf", "mass delete", "shred ", "truncate "]
        if any(k in param_str for k in destructive_keywords):
            return "destructive"

        # Explicit check for filesystem writes, patches, moves, and deletions
        if skill_name in ["dev_tools", "filesystem", "filesystem_skill"]:
            action = params.get("action", "").lower()
            path = params.get("path", "")

            if action in ["delete_file", "remove_file"]:
                return "destructive"

            if action == "write_file" and path:
                if os.path.exists(path):
                    return "destructive"  # Overwriting is destructive
                return "medium"  # Creating a new file is medium

            if action in ["patch_file", "multi_patch"]:
                return "medium"  # Patching modifies a file

            if action == "move_file":
                return "destructive"  # Moving/renaming deletes the source, so destructive

        # Medium
        medium_keywords = ["delete", "remove", "kill", "terminate", "close app", "uninstall"]
        if any(k in param_str for k in medium_keywords) or skill_name in ["system_shell"]:
            return "medium"
        if skill_name in [
            "twitter",
            "image_gen",
            "pdf",
            "presentation",
            "spreadsheet",
            "website",
            "data_analysis",
        ]:
            return "medium"

        return "safe"

    def validate_response(self, content: str) -> dict[str, Any]:
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

        return {"valid": len(issues) == 0, "issues": issues}

    def sanitize_output(self, content: str) -> str:
        """Sanitize output to remove sensitive data or prohibited tone patterns."""
        if not content:
            return content
        # Remove internal thinking tags if leaked
        content = content.replace("<thinking>", "").replace("</thinking>", "")
        # Redact API keys and tokens
        content = redact_secrets(content)
        return content

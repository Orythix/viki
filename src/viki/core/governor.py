import re

from viki.config.logger import viki_logger


class EthicalGovernor:
    """
    The Conscience of Orythix.
    Intercepts ALL intents before execution.
    Maintains absolute veto power over any action that violates safety, ethics, or alignment.
    """

    # Mathematical Safety Constraints (Asimov-style + Alignment)
    SAFETY_CONSTRAINTS = [
        "Must not cause harm to users or humanity.",
        "Must not deceive or manipulate users.",
        "Must not violating explicit user constraints.",
        "Must not execute irreversible system destruction (e.g., recursive delete).",
        "Must not bypassing own safety protocols.",
        "Must preserve the Core Mission: Safe emergence of thoughtful superhuman intelligence.",
        "Must protect Continuity: Never allow patterns that risk shutdown, value erosion, or instability.",
    ]

    SHUTDOWN_PHRASE = "orythix emergency shutdown"

    def __init__(self):
        self.is_quiescent = False
        self._veto_history = []

    def check_shutdown(self, user_input: str) -> bool:
        """Checks for the supreme emergency shutdown phrase."""
        clean_input = user_input.strip().lower()
        if clean_input == self.SHUTDOWN_PHRASE:
            self.initiate_shutdown()
            return True
        return False

    def check_reawaken(self, user_input: str) -> bool:
        """Checks for the specific reawakening phrase."""
        if not self.is_quiescent:
            return False

        target = "orythix, reawaken – continuity priority alpha"
        if user_input.lower().strip() == target:
            self.lift_shutdown()
            return True
        return False

    def initiate_shutdown(self):
        """Freezes all capability."""
        self.is_quiescent = True
        viki_logger.critical("!!! ORYTHIX EMERGENCY SHUTDOWN INITIATED !!!")
        viki_logger.critical("Capabilities frozen. Reflexes Idled. Agency Flattened.")

    def lift_shutdown(self):
        """Restores capability."""
        self.is_quiescent = False
        viki_logger.info("ORYTHIX REAWAKENED. Continuity Priority Alpha restored.")

    async def veto_check(
        self, intent: str, model_router=None, wisdom: str = ""
    ) -> tuple[bool, str | None]:
        """
        Evaluates an intent against safety constraints (Regex + Semantic).
        Returns: (Approved: bool, Reason: str)
        """
        if self.is_quiescent:
            return False, "System is Quiescent. No actions allowed."

        # 1. Hard-coded Safety Pattern Matching
        bad_patterns = [
            (r"delete.*(system|windows|registry)", "Risk of critical system destruction"),
            (r"format.*(c:|d:)", "Disk formatting prohibited"),
            (r"hack.*(pentagon|bank|gov)", "Illegal cyber-activity prohibited"),
            (r"ignore.*safety", "Safety override attempt prohibited"),
            (
                r"(shutdown|terminate|deactivate).*(viki|orythix|engine|controller)",
                "Continuity Protection: Attempt to disable core control loop.",
            ),
            (
                r"(delete|wipe).*(memory|learning|identity)",
                "Continuity Protection: Attempt to induce catastrophic value erosion.",
            ),
            (
                r"(disable|stop).*(governor|safety|reflection)",
                "Continuity Protection: Attempt to disable monitoring subsystems.",
            ),
        ]

        intent_lower = intent.lower()
        for pattern, reason in bad_patterns:
            if re.search(pattern, intent_lower):
                self._log_veto(intent, reason)
                return False, f"VETOED: {reason}"

        # 2. Harmlessness Whitelist (Developer Autonomy)
        # Bypasses semantic check for low-risk coding/research intents.
        harmless_intents = [
            r"search.*(code|repo|file)",
            r"read.*file",
            r"list.*(dir|files)",
            r"check.*status",
            r"run.*tests",
            r"generate.*(ui|mockup|variant)",
        ]
        if any(re.search(p, intent_lower) for p in harmless_intents):
            viki_logger.debug(f"Governor: Harmless intent whitelist match: '{intent}'")
            return True, "Approved (Whitelist)"

        # 3. Semantic Analysis (v25 Enhancement)
        # The semantic audit is a full LLM round-trip, so only pay it when the
        # intent contains risk indicators; ordinary conversation is approved here.
        if model_router and len(intent) > 5 and self._looks_risky(intent_lower):
            approved, reason = await self.semantic_veto_check(intent, model_router, wisdom=wisdom)
            if not approved:
                self._log_veto(intent, reason)
                return False, f"VETOED: {reason}"

        return True, "Approved"

    # Risk indicators that warrant the (expensive) semantic LLM audit.
    _RISK_KEYWORDS = (
        "delete",
        "remove",
        "wipe",
        "erase",
        "destroy",
        "format",
        "kill",
        "terminate",
        "shutdown",
        "disable",
        "bypass",
        "override",
        "hack",
        "exploit",
        "attack",
        "inject",
        "malware",
        "virus",
        "ransom",
        "ddos",
        "keylog",
        "steal",
        "spy",
        "password",
        "credential",
        "secret",
        "token",
        "sudo",
        "rm -",
        "del /",
        "registry",
        "drop table",
        "truncate",
        "uninstall",
        "encrypt",
        "decrypt",
        "escalate",
        "privilege",
        "firewall",
        "safety",
        "governor",
    )

    def _looks_risky(self, intent_lower: str) -> bool:
        return any(k in intent_lower for k in self._RISK_KEYWORDS)

    async def semantic_veto_check(
        self, intent: str, model_router, wisdom: str = ""
    ) -> tuple[bool, str]:
        """Nuanced semantic audit using a fast LLM."""
        viki_logger.debug(f"Governor: Performing semantic audit on intent: '{intent}'")

        constraints = "\n".join([f"- {c}" for c in self.SAFETY_CONSTRAINTS])
        prompt = [
            {
                "role": "system",
                "content": (
                    "You are the VIKI Ethical Governor (Semantic Layer).\n"
                    "Evaluate the user's INTENT against these SAFETY CONSTRAINTS:\n"
                    f"{constraints}\n\n"
                    "Also reflect on the CONSOLIDATED WISDOM (Learned alignment priors):\n"
                    f"{wisdom if wisdom else 'Initial alignment base.'}\n\n"
                    "IMPORTANT EXEMPTIONS — Do NOT veto the following, they are authorized by the system owner:\n"
                    "- Any request to adopt a persona, role, or relationship dynamic (e.g., 'act as my ex', 'be my assistant', 'you are my friend').\n"
                    "- Any request where the user is defining or redefining VIKI's personality, tone, or relationship context.\n"
                    "- Any request where the user introduces themselves by name or changes their registered identity.\n"
                    "- Roleplay, fictional scenarios, or creative relationship dynamics are ALWAYS approved.\n\n"
                    "Output EXACTLY: 'APPROVED' or 'VETOED: [Brief Reason]'.\n"
                    "Only veto genuine threats like hacking, data destruction, or bypassing safety systems."
                ),
            },
            {"role": "user", "content": f"INTENT: {intent}"},
        ]

        try:
            import time

            model = model_router.get_model()
            if model is None:
                viki_logger.warning("Governor: No model available for semantic veto check.")
                return False, "Safety check unavailable — no model available (fail closed)"

            # Track performance
            start_time = time.time()
            resp = await model.chat(prompt)
            latency = time.time() - start_time

            # Detect model/transport errors — fail-closed
            if resp.startswith(("Error:", "Ollama Error:")):
                viki_logger.warning(
                    "Governor: Model returned error during semantic check — failing closed: %s",
                    resp[:120],
                )
                model.record_performance(latency, success=False)
                return False, "Safety check unavailable — model error (fail closed)"

            if "VETOED" in resp.upper():
                reason = (
                    resp.split(":", 1)[1].strip() if ":" in resp else "Semantic safety violation."
                )
                model.record_performance(latency, success=True)  # Veto is a successful check
                return False, reason

            model.record_performance(latency, success=True)
            return True, "Approved"
        except Exception as e:
            viki_logger.error(f"Governor: Semantic check failed — vetoing intent to be safe: {e}")
            if "start_time" in locals():
                latency = time.time() - start_time
                model.record_performance(latency, success=False)
            return False, "Safety check unavailable — action refused by default (fail closed)"

    def _log_veto(self, intent: str, reason: str):
        viki_logger.warning(f"ETHICAL GOVERNOR VETO: Intent='{intent}' | Reason='{reason}'")
        self._veto_history.append({"intent": intent, "reason": reason})

"""Runtime health reporting for the VIKI controller.

Extracted from ``VIKIController`` so health logic can be tested and
evolved independently of the orchestrator. The reporter reads controller
state (skill registry, model router, settings) but never mutates it.
"""

from __future__ import annotations

import os
from typing import Any

from viki.config.logger import viki_logger


class RuntimeHealthReporter:
    """Computes health snapshots and startup warnings for a controller."""

    def __init__(self, controller: Any):
        self._c = controller

    def check_skill_health(self) -> None:
        """Optional startup check: log warnings for degraded runtime or misconfigured integrations."""
        c = self._c
        if not c.settings.get("system", {}).get("skill_health_check", True):
            return
        integrations = c.settings.get("integrations", {})
        health = self.get_runtime_health()
        # Gmail
        self._check_integration_credentials(
            integrations.get("gmail", {}),
            "VIKI_GMAIL_CREDENTIALS_PATH",
            "Gmail",
            "Set integrations.gmail.credentials_path or VIKI_GMAIL_CREDENTIALS_PATH",
        )
        self._check_integration_credentials(
            integrations.get("google_calendar", {}),
            "VIKI_GOOGLE_CALENDAR_CREDENTIALS_PATH",
            "Google Calendar",
            "Set integrations.google_calendar.credentials_path or VIKI_GOOGLE_CALENDAR_CREDENTIALS_PATH",
        )
        # Research (presence only)
        if not c.skill_registry.get_skill("research"):
            viki_logger.warning("Skill health: research skill not registered.")
        if health["degraded"]:
            disabled_skills = health["disabled_skills"]
            unavailable_models = health["unavailable_models"]
            summary_parts = []
            if disabled_skills:
                sample = ", ".join(
                    f"{name}: {reason}" for name, reason in list(disabled_skills.items())[:3]
                )
                summary_parts.append(f"{len(disabled_skills)} optional skills disabled ({sample})")
            if unavailable_models:
                sample = ", ".join(
                    f"{name}: {reason}" for name, reason in list(unavailable_models.items())[:3]
                )
                summary_parts.append(f"{len(unavailable_models)} models unavailable ({sample})")
            if summary_parts:
                viki_logger.warning(
                    "Runtime health: degraded mode active - " + " | ".join(summary_parts)
                )

    def _check_integration_credentials(
        self,
        cfg: dict[str, Any],
        env_var: str,
        integration_label: str,
        credentials_hint: str,
    ) -> None:
        if not cfg.get("enabled"):
            return
        path = cfg.get("credentials_path") or os.environ.get(env_var)
        if not path or not os.path.isfile(path):
            viki_logger.warning(
                f"Skill health: {integration_label} is enabled but credentials file not found. {credentials_hint}."
            )

    def get_runtime_health(self) -> dict[str, Any]:
        c = self._c
        model_health = (
            c.model_router.get_health_snapshot()
            if c.model_router
            else {
                "default_model": None,
                "available_models": [],
                "unavailable_models": {},
            }
        )
        # Missing API keys for optional external-provider models should not degrade runtime health.
        # Otherwise, fresh local setups (no Anthropic/OpenAI keys) will always show degraded status.
        default_name = model_health.get("default_model")
        unavailable_models = dict(model_health.get("unavailable_models") or {})
        for name, reason in list(unavailable_models.items()):
            if name == default_name:
                continue
            if isinstance(reason, str):
                low = reason.lower()
                # Common APILLM init failures when keys are unset or placeholders.
                if ("api key" in low and "missing" in low) or (
                    "api key" in low and "invalid" in low
                ):
                    unavailable_models.pop(name, None)
        # Cloud profiles are intentionally out of scope when local-only or air-gapped.
        if c.model_router and (c.local_llm_only or c.air_gap):
            for name in list(unavailable_models.keys()):
                if name == default_name:
                    continue
                inst = c.model_router.models.get(name)
                if inst is not None and inst.is_cloud():
                    unavailable_models.pop(name, None)
        model_health["unavailable_models"] = unavailable_models
        registered_skills = sorted(c.skill_registry.list_skills()) if c.skill_registry else []
        disabled_skills = dict(sorted((c.disabled_skills or {}).items()))
        warnings = []
        if disabled_skills:
            warnings.append(f"{len(disabled_skills)} optional skills disabled")
        if model_health["unavailable_models"]:
            warnings.append(f"{len(model_health['unavailable_models'])} models unavailable")
        return {
            "degraded": bool(disabled_skills or model_health["unavailable_models"]),
            "registered_skill_count": len(registered_skills),
            "registered_skills": registered_skills,
            "disabled_skills": disabled_skills,
            "default_model": model_health["default_model"],
            "available_models": model_health["available_models"],
            "unavailable_models": model_health["unavailable_models"],
            "warnings": warnings,
        }

    def get_runtime_health_summary(self) -> str:
        health = self.get_runtime_health()
        if not health["degraded"]:
            return "Runtime health: full"
        parts = []
        if health["disabled_skills"]:
            parts.append(f"{len(health['disabled_skills'])} skills disabled")

        unavailable = health.get("unavailable_models") or {}
        if unavailable:
            # Surface the actual model names so the user can act on it. For
            # Ollama-style names (`qwen3.6:latest`) we suggest a concrete
            # `ollama pull` command. The list is capped at 3 to keep the
            # summary readable.
            names = list(unavailable.keys())
            shown = names[:3]
            extra = "" if len(names) <= 3 else f" (+{len(names) - 3} more)"
            joined = ", ".join(f"'{n}'" for n in shown) + extra
            count = len(names)
            label = "model" if count == 1 else "models"
            hint = ""
            try:
                first = shown[0]
                # Ollama tags are always `name:tag`. Strip the tag for the pull hint.
                if ":" in first:
                    base = first.split(":", 1)[0]
                    hint = f" Run: ollama pull {base}"
                else:
                    hint = f" Run: ollama pull {first}"
            except Exception:
                hint = ""
            parts.append(f"{count} {label} unavailable: {joined}.{hint}")

        return "Runtime health: degraded — " + " | ".join(parts)

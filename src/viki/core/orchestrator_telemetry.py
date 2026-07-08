"""Session usage, router telemetry, and runtime health reporting.

Extracted from the VIKIController god-module; mixed into
viki.core.orchestrator.VIKIController.
"""

import os
from typing import Any

from viki.config.logger import viki_logger


class ControllerTelemetryMixin:
    def track_touched_item(self, category: str, item: str):
        """Track a file, command, or domain for the session dashboard."""
        if category not in self.session_history:
            return
        # Redact before storing if it's a command or file with potentially sensitive name
        redacted = self.safety.sanitize_output(item)
        if redacted not in self.session_history[category]:
            self.session_history[category].insert(0, redacted)
            self.session_history[category] = self.session_history[category][:10]

    def get_sovereign_status(self) -> dict[str, Any]:
        """Returns a snapshot of the current security and boundary status."""
        workspace_dir = self.settings.get("system", {}).get(
            "workspace_dir", self.DEFAULT_WORKSPACE_DIR
        )
        data_dir = self.settings.get("system", {}).get("data_dir", self.DEFAULT_DATA_DIR)

        shell_cap = self.capabilities.get("shell_exec")
        research_cap = self.capabilities.get("internet_research")

        return {
            "filesystem": {
                "workspace": os.path.abspath(workspace_dir),
                "data": os.path.abspath(data_dir),
                "allowed_roots_count": len(self.settings.get("system", {}).get("allowed_roots", []))
                or 2,
            },
            "network": {
                "air_gap": self.air_gap,
                "local_llm_only": self.settings.get("system", {}).get("local_llm_only", False),
                "allowlist_count": len(research_cap.meta.get("destination_allowlist", []))
                if research_cap
                else 0,
            },
            "shell": {
                "enabled": shell_cap.enabled if shell_cap else False,
                "approval_required": shell_cap.requires_confirmation if shell_cap else True,
            },
            "privacy": {"redaction_active": True, "shadow_mode": self.shadow_mode},
            "history": self.session_history,
        }

    def get_runtime_health(self) -> dict[str, Any]:
        return self.health_reporter.get_runtime_health()

    def get_runtime_health_summary(self) -> str:
        return self.health_reporter.get_runtime_health_summary()

    def _normalize_session_id(self, session_id: str | None = None) -> str:
        return session_id or getattr(self.memory.working, "default_session_id", "default")

    def get_last_response_meta(self, session_id: str | None = None) -> dict[str, Any]:
        session_id = self._normalize_session_id(session_id)
        meta = dict(self._last_response_meta_by_session.get(session_id, {}))
        usage = self._session_llm_usage.get(session_id)
        if usage:
            meta["usage"] = {
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "total_cost_usd": round(float(usage.get("total_cost_usd", 0.0)), 6),
                "by_model": dict(usage.get("by_model") or {}),
            }
        return meta

    def get_session_usage(self, session_id: str | None = None) -> dict[str, Any]:
        """Rolling LLM usage for this session (tokens + estimated USD)."""
        session_id = self._normalize_session_id(session_id)
        u = self._session_llm_usage.get(session_id)
        if not u:
            return {
                "session_id": session_id,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_cost_usd": 0.0,
                "by_model": {},
            }
        return {
            "session_id": session_id,
            "input_tokens": int(u.get("input_tokens", 0)),
            "output_tokens": int(u.get("output_tokens", 0)),
            "total_cost_usd": round(float(u.get("total_cost_usd", 0.0)), 6),
            "by_model": dict(u.get("by_model") or {}),
        }

    def reset_session_usage(self, session_id: str | None = None) -> None:
        session_id = self._normalize_session_id(session_id)
        self._session_llm_usage.pop(session_id, None)

    def _router_usage_snapshot(self) -> dict[str, tuple[int, int, float]]:
        snap: dict[str, tuple[int, int, float]] = {}
        try:
            for name, model in (self.model_router.models or {}).items():
                snap[name] = (
                    int(getattr(model, "input_tokens", 0) or 0),
                    int(getattr(model, "output_tokens", 0) or 0),
                    float(getattr(model, "total_cost_usd", 0.0) or 0.0),
                )
        except Exception as e:
            viki_logger.debug("_router_usage_snapshot: %s", e)
        return snap

    def _accumulate_session_usage_from_delta(
        self,
        session_id: str,
        baseline: dict[str, tuple[int, int, float]],
    ) -> None:
        sid = self._normalize_session_id(session_id)
        bucket = self._session_llm_usage.setdefault(
            sid,
            {"input_tokens": 0, "output_tokens": 0, "total_cost_usd": 0.0, "by_model": {}},
        )
        by_model: dict[str, Any] = bucket.setdefault("by_model", {})
        try:
            for name, model in (self.model_router.models or {}).items():
                cur = (
                    int(getattr(model, "input_tokens", 0) or 0),
                    int(getattr(model, "output_tokens", 0) or 0),
                    float(getattr(model, "total_cost_usd", 0.0) or 0.0),
                )
                b = baseline.get(name, (0, 0, 0.0))
                di, dout, dc = cur[0] - b[0], cur[1] - b[1], cur[2] - b[2]
                if di or dout or dc:
                    bucket["input_tokens"] = int(bucket.get("input_tokens", 0)) + di
                    bucket["output_tokens"] = int(bucket.get("output_tokens", 0)) + dout
                    bucket["total_cost_usd"] = float(bucket.get("total_cost_usd", 0.0)) + dc
                    bm = by_model.setdefault(
                        name,
                        {"input_tokens": 0, "output_tokens": 0, "total_cost_usd": 0.0},
                    )
                    bm["input_tokens"] = int(bm.get("input_tokens", 0)) + di
                    bm["output_tokens"] = int(bm.get("output_tokens", 0)) + dout
                    bm["total_cost_usd"] = float(bm.get("total_cost_usd", 0.0)) + dc
        except Exception as e:
            viki_logger.debug("_accumulate_session_usage_from_delta: %s", e)

    def get_router_telemetry(self) -> dict[str, Any]:
        """Return cognitive routing telemetry (reflex hit rate, per-outcome counts)."""
        try:
            return self.router_telemetry.snapshot()
        except Exception as e:
            viki_logger.debug("get_router_telemetry: %s", e)
            return {"error": str(e)}

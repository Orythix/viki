"""
Cost & circuit-breaker enforcement for cloud LLM providers.

The router consults `LLMBudget` before each cloud call. The budget tracks
daily USD spend and per-call caps. A separate `CircuitBreaker` per provider
short-circuits calls when a provider has failed repeatedly so the router
can fail over fast.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, Optional

from viki.config.logger import viki_logger


_DEFAULT_BUDGET = {
    "daily_usd_cap": 5.00,
    "per_call_usd_cap": 0.50,
    "per_provider_daily_cap": {},
    "explicit_cloud_only": False,
}


@dataclass
class CircuitBreakerState:
    failures: int = 0
    last_failure_ts: float = 0.0
    open_until_ts: float = 0.0
    cooldown_seconds: float = 30.0
    failure_threshold: int = 3

    def is_open(self) -> bool:
        return time.time() < self.open_until_ts

    def record_success(self) -> None:
        self.failures = 0
        self.open_until_ts = 0.0

    def record_failure(self) -> None:
        self.failures += 1
        self.last_failure_ts = time.time()
        if self.failures >= self.failure_threshold:
            self.open_until_ts = time.time() + self.cooldown_seconds
            viki_logger.warning(
                "CircuitBreaker tripped (failures=%d) — cooldown for %.0fs.",
                self.failures,
                self.cooldown_seconds,
            )

    def half_open_probe(self) -> None:
        # Allow a single probe after cooldown.
        self.failures = max(0, self.failure_threshold - 1)


class LLMBudget:
    """Daily cost cap + per-call cap + provider circuit breakers."""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        state_path: Optional[str] = None,
    ):
        self._lock = threading.Lock()
        self.config = {**_DEFAULT_BUDGET, **(config or {})}
        self.state_path = state_path
        self._today: str = date.today().isoformat()
        self._spent_today: float = 0.0
        self._spent_by_provider: Dict[str, float] = {}
        self._breakers: Dict[str, CircuitBreakerState] = {}
        self._explicit_cloud_override: bool = False
        self._load_state()

    # --- persistence ---
    def _load_state(self) -> None:
        if not self.state_path or not os.path.exists(self.state_path):
            return
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            if data.get("date") == self._today:
                self._spent_today = float(data.get("spent_today", 0.0))
                self._spent_by_provider = dict(data.get("spent_by_provider", {}))
        except Exception as e:
            viki_logger.debug("LLMBudget load: %s", e)

    def _save_state(self) -> None:
        if not self.state_path:
            return
        try:
            os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "date": self._today,
                        "spent_today": round(self._spent_today, 6),
                        "spent_by_provider": {
                            k: round(v, 6) for k, v in self._spent_by_provider.items()
                        },
                    },
                    f,
                )
        except Exception as e:
            viki_logger.debug("LLMBudget save: %s", e)

    def _maybe_rollover(self) -> None:
        today = date.today().isoformat()
        if today != self._today:
            viki_logger.info(
                "LLMBudget: day rollover (%s -> %s); resetting daily spend.",
                self._today,
                today,
            )
            self._today = today
            self._spent_today = 0.0
            self._spent_by_provider = {}
            self._save_state()

    # --- public API ---
    def set_explicit_cloud(self, on: bool) -> None:
        self._explicit_cloud_override = bool(on)

    def get_breaker(self, provider_name: str) -> CircuitBreakerState:
        with self._lock:
            if provider_name not in self._breakers:
                self._breakers[provider_name] = CircuitBreakerState()
            return self._breakers[provider_name]

    def can_spend(
        self,
        provider_name: str,
        estimated_usd: float,
        is_cloud: bool,
    ) -> tuple:
        """Return (allowed: bool, reason: str)."""
        with self._lock:
            self._maybe_rollover()

            if not is_cloud:
                return True, ""

            if (
                self.config.get("explicit_cloud_only")
                and not self._explicit_cloud_override
            ):
                return False, "Cloud calls require explicit_cloud override."

            per_call_cap = float(self.config.get("per_call_usd_cap", 0.50))
            if estimated_usd > per_call_cap:
                return (
                    False,
                    f"Per-call cost ${estimated_usd:.4f} exceeds cap ${per_call_cap:.4f}.",
                )

            daily_cap = float(self.config.get("daily_usd_cap", 5.00))
            if self._spent_today + estimated_usd > daily_cap:
                return (
                    False,
                    f"Daily cloud budget exhausted (${self._spent_today:.4f}/${daily_cap:.4f}).",
                )

            per_provider_caps = self.config.get("per_provider_daily_cap") or {}
            provider_cap = per_provider_caps.get(provider_name)
            if provider_cap is not None:
                used = self._spent_by_provider.get(provider_name, 0.0)
                if used + estimated_usd > float(provider_cap):
                    return (
                        False,
                        f"Provider {provider_name} daily cap reached (${used:.4f}/${provider_cap:.4f}).",
                    )

            breaker = self._breakers.setdefault(provider_name, CircuitBreakerState())
            if breaker.is_open():
                return (
                    False,
                    f"Provider {provider_name} circuit breaker is open (cooldown).",
                )

            return True, ""

    def record_cost(self, provider_name: str, usd: float) -> None:
        with self._lock:
            self._maybe_rollover()
            self._spent_today += float(usd)
            self._spent_by_provider[provider_name] = (
                self._spent_by_provider.get(provider_name, 0.0) + float(usd)
            )
            self._save_state()

    def record_failure(self, provider_name: str) -> None:
        with self._lock:
            breaker = self._breakers.setdefault(provider_name, CircuitBreakerState())
            breaker.record_failure()

    def record_success(self, provider_name: str) -> None:
        with self._lock:
            breaker = self._breakers.setdefault(provider_name, CircuitBreakerState())
            breaker.record_success()

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            self._maybe_rollover()
            return {
                "date": self._today,
                "spent_today": round(self._spent_today, 6),
                "daily_cap": float(self.config.get("daily_usd_cap", 5.00)),
                "per_call_cap": float(self.config.get("per_call_usd_cap", 0.50)),
                "spent_by_provider": dict(self._spent_by_provider),
                "circuit_breakers": {
                    name: {
                        "failures": b.failures,
                        "open": b.is_open(),
                        "open_until_ts": b.open_until_ts,
                    }
                    for name, b in self._breakers.items()
                },
                "explicit_cloud_override": self._explicit_cloud_override,
            }

"""ModelRouter — selects optimal LLM based on capabilities, tier, and health."""

from __future__ import annotations

import time
from typing import Any

import yaml

from viki.config.logger import viki_logger

from .api_llm import APILLM
from .fallback_llm import FallbackLLM
from .llm_provider import LLMProvider
from .local_llm import LocalLLM
from .model_factory import ModelFactory
from .utils import effective_profile_for_factory


class ModelRouter:
    CONSECUTIVE_FAIL_THRESHOLD = 3
    COOLDOWN_SECONDS = 60

    def __init__(
        self,
        config_path: str,
        air_gap: bool = False,
        local_llm_only: bool = False,
        budget=None,
        system_settings: dict[str, Any] | None = None,
    ):
        self.models = {}
        self.default_model = None
        self.air_gap = air_gap
        self.local_llm_only = local_llm_only
        self.budget = budget
        self._budget_config: dict[str, Any] = {}
        self._system_settings = system_settings
        self._model_cooldowns: dict[str, dict[str, Any]] = {}
        self._load_config(config_path)

    def _model_allowed(self, model: LLMProvider) -> bool:
        if not model.available:
            return False
        if model.config.get("training_only"):
            return False
        if self._model_on_cooldown(model.model_name):
            return False
        try:
            cloud = model.is_cloud()
        except Exception:
            cloud = isinstance(model, APILLM)
        if self.air_gap and cloud:
            return False
        if self.local_llm_only and cloud:
            return False
        if self.budget is not None and cloud:
            try:
                breaker = self.budget.get_breaker(getattr(model, "provider_name", "unknown"))
                if breaker.is_open():
                    return False
            except Exception:
                pass
        return True

    def _model_on_cooldown(self, model_name: str) -> bool:
        entry = self._model_cooldowns.get(model_name)
        if not entry:
            return False
        if time.time() >= entry["cooldown_until"]:
            del self._model_cooldowns[model_name]
            return False
        return True

    def record_model_failure(self, model_name: str):
        now = time.time()
        entry = self._model_cooldowns.setdefault(
            model_name, {"consecutive_failures": 0, "cooldown_until": 0}
        )
        entry["consecutive_failures"] += 1
        if entry["consecutive_failures"] >= self.CONSECUTIVE_FAIL_THRESHOLD:
            entry["cooldown_until"] = now + self.COOLDOWN_SECONDS
            viki_logger.warning(
                "Model '%s' failed %d times; cooling down for %ds",
                model_name,
                self.CONSECUTIVE_FAIL_THRESHOLD,
                self.COOLDOWN_SECONDS,
            )

    def record_model_success(self, model_name: str):
        self._model_cooldowns.pop(model_name, None)

    def _first_allowed_model(self) -> LLMProvider | None:
        for m in self.models.values():
            if self._model_allowed(m):
                return m
        for m in self.models.values():
            if m.available and isinstance(m, LocalLLM):
                return m
        for m in self.models.values():
            if m.available:
                return m
        return None

    def _load_config(self, path: str):
        try:
            with open(path) as f:
                config = yaml.safe_load(f)
            providers = config.get("models", {}).get("providers", {})
            profiles = config.get("models", {}).get("profiles", {})
            default_profile = config.get("models", {}).get("default", "mock-model")
            self._budget_config = dict(config.get("models", {}).get("budget", {}) or {})

            if self.budget is None and self._budget_config:
                try:
                    from viki.core.resource_budget import LLMBudget

                    self.budget = LLMBudget(self._budget_config)
                except Exception as e:
                    viki_logger.debug("Failed to init LLMBudget: %s", e)

            for name, profile in profiles.items():
                provider_name = profile.get("provider")
                if provider_name in providers:
                    provider_conf = providers[provider_name]
                    merged_provider_conf = {**provider_conf, "provider": provider_name}
                    eff_profile = effective_profile_for_factory(
                        profile, merged_provider_conf, self._system_settings
                    )
                    self.models[name] = ModelFactory.create(name, eff_profile, merged_provider_conf)

            preferred: LLMProvider | None = None
            if default_profile in self.models:
                preferred = self.models[default_profile]
            elif self.models:
                preferred = list(self.models.values())[0]

            if preferred and self._model_allowed(preferred):
                self.default_model = preferred
            else:
                self.default_model = self._first_allowed_model() or FallbackLLM(
                    {"model_name": "fallback-mock"}
                )
                if preferred and not preferred.available:
                    viki_logger.warning(
                        "Default model profile '%s' is unavailable (%s). Using '%s' instead.",
                        default_profile,
                        getattr(preferred, "unavailable_reason", "unknown"),
                        getattr(self.default_model, "model_name", "fallback"),
                    )
        except (OSError, yaml.YAMLError, FileNotFoundError, KeyError) as e:
            viki_logger.error(f"Failed to load model config from {path}: {e}")
            self.default_model = FallbackLLM({"model_name": "error-fallback"})

    def get_model(self, capabilities: list[str] = None, tier: str = "standard") -> LLMProvider:
        if not capabilities and tier == "standard":
            if self._model_allowed(self.default_model):
                return self.default_model
            fb = self._first_allowed_model()
            return fb or self.default_model

        best_candidate = None
        best_score = -1
        for model in self.models.values():
            if not self._model_allowed(model):
                continue
            model_caps = model.config.get("capabilities", [])
            model_tier = model.config.get("tier", "standard").lower()
            matched_caps = sum(1 for cap in (capabilities or []) if cap in model_caps)
            priority = model.config.get("priority", 2)
            score = (matched_caps * priority) + (model.trust_score * 0.5)
            if model_tier == tier.lower():
                score += 10.0
            is_fast = "fast_response" in (capabilities or []) or tier == "fast"
            if is_fast and model.avg_latency > 0:
                score -= model.avg_latency / 10.0
            if model.call_count > 10:
                error_rate = model.error_count / model.call_count
                score -= error_rate * 5.0
            if score > best_score:
                best_score = score
                best_candidate = model

        if best_candidate:
            return best_candidate
        if self._model_allowed(self.default_model):
            return self.default_model
        return self._first_allowed_model() or self.default_model

    def get_health_snapshot(self) -> dict[str, Any]:
        available = []
        unavailable = {}
        for name, model in self.models.items():
            if model.available:
                available.append(name)
            else:
                unavailable[name] = model.unavailable_reason or "unavailable"
        default_name = None
        for name, model in self.models.items():
            if model is self.default_model:
                default_name = name
                break
        return {
            "default_model": default_name,
            "available_models": available,
            "unavailable_models": unavailable,
            "budget": self.budget.snapshot() if self.budget is not None else {},
        }

    def apply_eval_signal(self, model_name: str, pass_rate: float) -> None:
        model = self.models.get(model_name)
        if model is None:
            return
        prev = float(getattr(model, "trust_score", 1.0))
        updated = max(0.0, min(1.0, 0.7 * prev + 0.3 * float(pass_rate)))
        model.trust_score = updated

    def get_failover_chain(
        self, capabilities: list[str] | None = None, max_models: int = 4
    ) -> list[LLMProvider]:
        scored: list[tuple] = []
        for model in self.models.values():
            if not self._model_allowed(model):
                continue
            model_caps = model.config.get("capabilities", [])
            matched = sum(1 for cap in (capabilities or []) if cap in model_caps)
            priority = model.config.get("priority", 2)
            score = (matched * priority) + (model.trust_score * 0.5)
            if model.call_count > 10:
                error_rate = model.error_count / model.call_count
                score -= error_rate * 5.0
            scored.append((score, model))
        scored.sort(key=lambda x: -x[0])
        return [m for _, m in scored[:max_models]]

    @staticmethod
    def _looks_like_error(text: Any) -> bool:
        if not isinstance(text, str):
            return False
        prefixes = (
            "Error calling API Model:",
            "Error calling Local Model:",
            "Error calling Gemini Model:",
            "Error calling Groq Model:",
            "Error calling Mistral Model:",
            "Error calling Bedrock Model:",
            "Error: Model ",
        )
        return any(text.startswith(p) for p in prefixes)

    @staticmethod
    def _redact_messages_for_cloud(messages: list[dict[str, str]]) -> list[dict[str, str]]:
        try:
            from viki.core.security_guard import redact_secrets

            redacted: list[dict[str, str]] = []
            for m in messages:
                content = m.get("content")
                if isinstance(content, str):
                    redacted.append({**m, "content": redact_secrets(content)})
                elif isinstance(content, list):
                    parts = []
                    for part in content:
                        if isinstance(part, dict) and isinstance(part.get("text"), str):
                            parts.append({**part, "text": redact_secrets(part["text"])})
                        else:
                            parts.append(part)
                    redacted.append({**m, "content": parts})
                else:
                    redacted.append(m)
            return redacted
        except Exception:
            return messages

    async def chat_with_failover(
        self,
        messages: list[dict[str, str]],
        capabilities: list[str] | None = None,
        temperature: float = 0.7,
        max_attempts: int = 3,
    ) -> dict[str, Any]:
        chain = self.get_failover_chain(capabilities, max_models=max_attempts)
        if not chain:
            chain = [self.get_model(capabilities)]
        errors: list[dict[str, Any]] = []
        for attempt, model in enumerate(chain):
            try:
                outbound = (
                    self._redact_messages_for_cloud(messages) if model.is_cloud() else messages
                )
                if self.budget is not None and model.is_cloud():
                    estimate = model.estimate_cost_usd(prompt_tokens=512, completion_tokens=256)
                    allowed, reason = self.budget.can_spend(
                        getattr(model, "provider_name", "unknown"),
                        estimate,
                        is_cloud=True,
                    )
                    if not allowed:
                        errors.append({"model": model.model_name, "reason": reason})
                        continue
                t0 = time.perf_counter()
                text = await model.chat(outbound, temperature=temperature)
                latency = time.perf_counter() - t0

                if self._looks_like_error(text):
                    model.record_performance(latency, False)
                    if self.budget is not None and model.is_cloud():
                        self.budget.record_failure(getattr(model, "provider_name", "unknown"))
                    errors.append({"model": model.model_name, "reason": text})
                    continue

                model.record_performance(latency, True)
                if self.budget is not None and model.is_cloud():
                    self.budget.record_success(getattr(model, "provider_name", "unknown"))
                    self.budget.record_cost(
                        getattr(model, "provider_name", "unknown"),
                        getattr(model, "total_cost_usd", 0.0),
                    )
                return {
                    "text": text,
                    "model_name": model.model_name,
                    "attempts": attempt + 1,
                    "errors": errors,
                }
            except Exception as e:
                if self.budget is not None and model.is_cloud():
                    self.budget.record_failure(getattr(model, "provider_name", "unknown"))
                errors.append({"model": model.model_name, "reason": str(e)})
                model.record_performance(0.0, False)
        return {"text": "", "model_name": None, "attempts": len(chain), "errors": errors}

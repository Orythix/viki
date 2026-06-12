"""Abstract base class for LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.model_name = config.get("model_name", "unknown")
        self.trust_score = 1.0
        self.strengths = config.get("strengths", [])
        self.weaknesses = config.get("weaknesses", [])
        self.error_count = 0
        self.avg_latency = 0.0
        self.call_count = 0
        self.available = True
        self.unavailable_reason = None
        self.cost_per_1k_in: float = float(config.get("cost_per_1k_in", 0.0))
        self.cost_per_1k_out: float = float(config.get("cost_per_1k_out", 0.0))
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.total_cost_usd: float = 0.0
        self.provider_name: str = config.get("provider", config.get("provider_type", "unknown"))

    def is_cloud(self) -> bool:
        return True

    def record_performance(self, latency: float, success: bool):
        self.call_count += 1
        n = self.call_count
        self.avg_latency = ((self.avg_latency * (n - 1)) + latency) / n
        if not success:
            self.error_count += 1
            self.trust_score = max(0.0, self.trust_score - 0.1)
        else:
            self.trust_score = min(1.0, self.trust_score + 0.01)
        try:
            from viki.core.usage_log import emit_model_feedback

            emit_model_feedback(self, latency, success)
        except Exception:
            pass

    def estimate_cost_usd(self, prompt_tokens: int, completion_tokens: int = 256) -> float:
        return (prompt_tokens / 1000.0) * self.cost_per_1k_in + (
            completion_tokens / 1000.0
        ) * self.cost_per_1k_out

    def record_token_usage(self, input_tokens: int, output_tokens: int) -> float:
        self.input_tokens += int(input_tokens or 0)
        self.output_tokens += int(output_tokens or 0)
        delta = (input_tokens / 1000.0) * self.cost_per_1k_in + (
            output_tokens / 1000.0
        ) * self.cost_per_1k_out
        self.total_cost_usd += delta
        try:
            from api.events import get_event_bus

            get_event_bus().publish(
                "usage",
                {"input": input_tokens, "output": output_tokens, "model": self.model_name},
                channel="system",
            )
        except Exception:
            pass
        return delta

    @abstractmethod
    async def chat(self, messages: list[dict[str, str]], temperature: float = 0.7) -> str:
        ...

    @abstractmethod
    async def chat_structured(
        self,
        messages: list[dict[str, str]],
        response_model: type[T],
        temperature: float = 0.0,
        image_path: str = None,
    ) -> T:
        ...

    async def chat_stream(self, messages: list[dict[str, str]], temperature: float = 0.7):
        result = await self.chat(messages, temperature=temperature)
        if result:
            yield result

"""Factory for creating LLM provider instances from config profiles."""

from __future__ import annotations

from typing import Any

from .api_llm import APILLM
from .fallback_llm import FallbackLLM
from .llm_provider import LLMProvider
from .local_llm import LocalLLM


class ModelFactory:
    @staticmethod
    def create(
        profile_name: str, profile_config: dict[str, Any], provider_config: dict[str, Any]
    ) -> LLMProvider:
        provider_type = provider_config.get("type", "mock")
        merged_config = {**provider_config, **profile_config}
        merged_config.setdefault("provider", provider_type)

        if provider_type == "mock":
            return FallbackLLM(merged_config)
        if provider_type == "api":
            return APILLM(merged_config)
        if provider_type == "anthropic":
            merged_config["type"] = "api"
            return APILLM(merged_config)
        if provider_type == "local":
            merged_config.setdefault("supports_native_tools", False)
            return LocalLLM(merged_config)
        if provider_type in ("gemini", "google", "vertex"):
            from viki.core.inference_providers import GeminiLLM

            return GeminiLLM(merged_config)
        if provider_type == "groq":
            from viki.core.inference_providers import GroqLLM

            return GroqLLM(merged_config)
        if provider_type == "mistral":
            from viki.core.inference_providers import MistralLLM

            return MistralLLM(merged_config)
        if provider_type in ("bedrock", "aws_bedrock"):
            from viki.core.inference_providers import BedrockLLM

            return BedrockLLM(merged_config)
        raise ValueError(f"Unknown provider type: {provider_type}")

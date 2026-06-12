"""V2 LLM client — simple Ollama wrapper."""

from __future__ import annotations

from .client import OllamaClient, get_llm_client

__all__ = ["OllamaClient", "get_llm_client"]

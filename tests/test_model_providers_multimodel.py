"""Unit tests for multi-provider model routing (LM Studio, Ollama, OpenAI, Claude, Gemini)."""

from __future__ import annotations

import yaml

from viki.core.model.model_factory import ModelFactory


def test_model_factory_provider_instantiation():
    conf = {
        "lmstudio-gemma": {"provider": "lmstudio", "model_name": "google/gemma-4-e4b"},
        "ollama-test": {"provider": "ollama", "model_name": "llama3.1:8b"},
        "api-openai": {"provider": "api", "model_name": "gpt-4o", "api_key": "test_key"},
    }

    p1 = ModelFactory.create("lmstudio-gemma", conf["lmstudio-gemma"], {"type": "lmstudio"})
    assert p1 is not None

    p2 = ModelFactory.create("ollama-test", conf["ollama-test"], {"type": "ollama"})
    assert p2 is not None


def test_models_yaml_profiles_integrity():
    with open("config/models.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    profiles = data["models"]["profiles"]
    assert "lmstudio-gemma4e4b" in profiles
    assert "ollama-llama3" in profiles
    assert "gemini-2-5-pro" in profiles
    assert "claude-3-7-sonnet" in profiles
    assert "gpt-4o" in profiles

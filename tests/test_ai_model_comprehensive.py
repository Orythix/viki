"""
Comprehensive Unit Tests for VIKI AI Model System.

Tests ModelFactory, ModelRouter, LocalLLM, APILLM, and InferenceProviders
across all local & cloud providers (LM Studio, Ollama, Gemini, Claude, OpenAI, Groq, Nvidia NIM, OpenCode).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from viki.core.inference_providers import (
    BedrockLLM,
    GeminiLLM,
    GroqLLM,
    MistralLLM,
    NvidiaLLM,
    OpenCodeLLM,
)
from viki.core.model.api_llm import APILLM
from viki.core.model.local_llm import LocalLLM
from viki.core.model.model_factory import ModelFactory
from viki.core.model.model_router import ModelRouter


def test_model_factory_all_providers():
    """Verify ModelFactory creates correct instances for all supported provider types."""
    providers = [
        ("lmstudio", LocalLLM),
        ("ollama", LocalLLM),
        ("api", APILLM),
        ("anthropic", APILLM),
        ("gemini", GeminiLLM),
        ("groq", GroqLLM),
        ("mistral", MistralLLM),
        ("nvidia_nim", NvidiaLLM),
        ("opencode", OpenCodeLLM),
        ("bedrock", BedrockLLM),
    ]

    for p_type, expected_cls in providers:
        config = {
            "model_name": "test-model",
            "type": p_type,
            "api_key": "test-key"
            if "api" in p_type
            or p_type
            in ("anthropic", "gemini", "groq", "mistral", "nvidia_nim", "opencode", "bedrock")
            else "",
            "base_url": "http://localhost:1234/v1" if p_type in ("lmstudio", "ollama") else "",
        }
        inst = ModelFactory.create("test-profile", config, {"type": p_type})
        assert isinstance(inst, expected_cls), (
            f"Provider {p_type} should create instance of {expected_cls}"
        )


def test_model_router_config_loading_and_filtering():
    """Test ModelRouter configuration parsing and filtering under air-gap and local-only modes."""
    router_airgap = ModelRouter(config_path="config/models.yaml", air_gap=True)
    assert router_airgap is not None
    assert router_airgap.air_gap is True

    # Under air-gap mode, cloud models should be disallowed by _model_allowed
    mock_cloud_model = MagicMock()
    mock_cloud_model.available = True
    mock_cloud_model.is_cloud.return_value = True
    mock_cloud_model.model_name = "gpt-4o"
    mock_cloud_model.config = {}

    assert router_airgap._model_allowed(mock_cloud_model) is False

    mock_local_model = MagicMock()
    mock_local_model.available = True
    mock_local_model.is_cloud.return_value = False
    mock_local_model.model_name = "lmstudio-gemma4e4b"
    mock_local_model.config = {}

    # Under local mode, local model should be allowed
    assert router_airgap._model_allowed(mock_local_model) is True


def test_local_llm_hostname_normalization():
    """Test LocalLLM converts localhost to 127.0.0.1 to prevent Windows IPv6 resolution latency."""
    config = {
        "base_url": "http://localhost:1234/v1",
        "model_name": "google/gemma-4-e4b",
    }
    llm = LocalLLM(config)
    assert "127.0.0.1" in llm.base_url
    assert llm.model_name == "google/gemma-4-e4b"


def test_api_llm_initialization():
    """Test APILLM initializes with correct model name and config."""
    config = {
        "model_name": "custom-api-model",
        "api_key": "sk-testkey12345",
        "base_url": "http://127.0.0.1:8000/v1",
    }
    llm = APILLM(config)
    assert llm.model_name == "custom-api-model"
    assert llm.config.get("api_key") == "sk-testkey12345"


def test_inference_providers_instances():
    """Test specialized inference provider class instantiation and attributes."""
    gemini = GeminiLLM({"model_name": "gemini-2.5-pro", "api_key": "gemini-key"})
    assert gemini.model_name == "gemini-2.5-pro"

    groq = GroqLLM({"model_name": "llama-3.3-70b-versatile", "api_key": "groq-key"})
    assert groq.model_name == "llama-3.3-70b-versatile"

    nvidia = NvidiaLLM(
        {"model_name": "nvidia/llama-3.1-nemotron-70b-instruct", "api_key": "nvapi-key"}
    )
    assert nvidia.model_name == "nvidia/llama-3.1-nemotron-70b-instruct"

    opencode = OpenCodeLLM({"model_name": "opencode/zen-coder", "api_key": "sk-opencode-key"})
    assert opencode.model_name == "opencode/zen-coder"

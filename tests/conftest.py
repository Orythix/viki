"""Pytest configuration and fixtures for VIKI tests."""

import sys
import tempfile
from pathlib import Path

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture(scope="session")
def temp_data_dir():
    """Create a temporary data directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture(scope="session")
def test_settings_path(temp_data_dir):
    """Create a minimal settings.yaml for testing."""
    settings_content = f"""
system:
  owner:
    name: "TestUser"
    role: "Developer"
  local_llm_only: true
  auto_web_research_when_uncertain: false

models_config: "./models.yaml"
security_layer_path: "./security_layer.md"

memory:
  data_dir: "{temp_data_dir}"
  working_memory_limit: 100
  episodic_memory_limit: 50

skills:
  enabled:
    - "filesystem"
    - "shell"
    - "memory"
    - "recall"
    - "research"

sovereign:
  air_gap: false
  shell_enabled: true
  shell_requires_confirmation: true
  allowed_roots: ["{temp_data_dir}"]
"""
    settings_path = Path(temp_data_dir) / "settings.yaml"
    settings_path.write_text(settings_content.strip())
    return str(settings_path)


@pytest.fixture(scope="session")
def test_models_path(temp_data_dir):
    """Create a minimal models.yaml for testing."""
    models_content = """
default_model: "lmstudio-gemma4e4b"
fallback_order:
  - "lmstudio-gemma4e4b"
  - "lmstudio-qwen3"

model_profiles:
  lmstudio-gemma4e4b:
    provider: "lmstudio"
    model_name: "google/gemma-4-e4b"
    temperature: 0.7
    capabilities: ["reasoning", "coding", "general"]
  lmstudio-qwen3:
    provider: "lmstudio"
    model_name: "qwen/qwen3.5-9b"
    temperature: 0.5
    capabilities: ["fast_response"]

task_routes:
  general:
    primary: "lmstudio-gemma4e4b"
    fallback: "lmstudio-qwen3"
  reasoning:
    primary: "lmstudio-gemma4e4b"
    fallback: "phi3:mini"
  coding:
    primary: "gemma4:12b"
    fallback: "phi3:mini"
  fast:
    primary: "phi3:mini"
"""
    models_path = Path(temp_data_dir) / "models.yaml"
    models_path.write_text(models_content.strip())
    return str(models_path)


@pytest.fixture(scope="session")
def test_security_path(temp_data_dir):
    """Create a minimal security_layer.md for testing."""
    security_content = """# Security Layer

## Redaction Rules
- API keys
- Passwords
- Personal tokens

## Allowed Operations
- File read/write in workspace
- Shell commands with confirmation
"""
    security_path = Path(temp_data_dir) / "security_layer.md"
    security_path.write_text(security_content.strip())
    return str(security_path)

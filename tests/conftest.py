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
default_model: "gemma4:12b"
fallback_order:
  - "gemma4:12b"
  - "phi3:mini"

model_profiles:
  gemma4:12b:
    provider: "ollama"
    model_name: "gemma4:12b"
    temperature: 0.7
    capabilities: ["reasoning", "coding", "general"]
  phi3:mini:
    provider: "ollama"
    model_name: "phi3:mini"
    temperature: 0.5
    capabilities: ["fast_response"]

task_routes:
  general:
    primary: "gemma4:12b"
    fallback: "phi3:mini"
  reasoning:
    primary: "gemma4:12b"
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

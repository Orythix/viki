"""Pytest fixtures for V2 unit tests."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from viki.v2.llm.client import OllamaClient


@pytest.fixture
def mock_llm():
    """Create a mock LLM client that returns structured data."""
    client = MagicMock(spec=OllamaClient)
    client.chat = AsyncMock(return_value="Mock response")
    client.structured_output = AsyncMock(
        return_value={
            "summary": "Test analysis",
            "confidence": 0.85,
            "risks": ["Risk 1"],
            "recommendations": ["Rec 1"],
        }
    )
    return client


@pytest.fixture
def mock_llm_planner():
    """Mock LLM that returns a valid TaskPlan."""
    client = MagicMock(spec=OllamaClient)
    client.structured_output = AsyncMock(
        return_value={
            "goal": "Test goal",
            "estimated_complexity": "low",
            "requires_confirmation": False,
            "steps": [
                {
                    "id": "step1",
                    "description": "First step",
                    "tool": "shell",
                    "params": {"command": "echo hello"},
                    "risk": "LOW",
                    "depends_on": [],
                    "timeout": 30,
                },
                {
                    "id": "step2",
                    "description": "Second step",
                    "tool": "shell",
                    "params": {"command": "echo world"},
                    "risk": "LOW",
                    "depends_on": ["step1"],
                    "timeout": 30,
                },
            ],
        }
    )
    client.chat = AsyncMock(return_value="Mock")
    return client


@pytest.fixture
def mock_llm_critique():
    """Mock LLM that returns a critique result."""
    client = MagicMock(spec=OllamaClient)
    client.structured_output = AsyncMock(
        return_value={
            "score": 0.6,
            "passed": False,
            "issues": [
                {"category": "correctness", "description": "Missing edge case", "severity": "high"}
            ],
        }
    )
    client.chat = AsyncMock(return_value="Improved solution")
    return client


@pytest.fixture
def temp_dir():
    """Provide a temporary directory path."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        yield Path(tmp)


@pytest.fixture
def mock_registry():
    """Create a mock ToolRegistry with shell and filesystem tools."""
    from unittest.mock import AsyncMock, MagicMock

    from viki.v2.tools.base import ToolResult
    from viki.v2.tools.registry import ToolRegistry

    registry = ToolRegistry()

    # Register a mock shell tool
    shell_tool = MagicMock()
    shell_tool.name = "shell"
    shell_tool.description = "Execute shell commands"
    shell_tool.capabilities = ["shell"]
    shell_tool.permission_tier = MagicMock()
    shell_tool.permission_tier.name = "ELEVATED"
    shell_tool.examples = []
    shell_tool.parameters = {}
    shell_tool.execute = AsyncMock(return_value=ToolResult(success=True, data="hello\nworld"))
    shell_tool.get_tool_definition = MagicMock(
        return_value={
            "type": "function",
            "function": {
                "name": "shell",
                "description": "Execute shell commands",
                "parameters": {},
            },
        }
    )
    registry.register(shell_tool)

    # Register a mock filesystem tool
    fs_tool = MagicMock()
    fs_tool.name = "filesystem"
    fs_tool.description = "File operations"
    fs_tool.capabilities = ["filesystem"]
    fs_tool.permission_tier = MagicMock()
    fs_tool.permission_tier.name = "SAFE"
    fs_tool.examples = []
    fs_tool.parameters = {}
    fs_tool.execute = AsyncMock(
        return_value=ToolResult(success=True, data={"files": ["a.py", "b.py"]})
    )
    fs_tool.get_tool_definition = MagicMock(
        return_value={
            "type": "function",
            "function": {
                "name": "filesystem",
                "description": "File operations",
                "parameters": {},
            },
        }
    )
    registry.register(fs_tool)

    return registry

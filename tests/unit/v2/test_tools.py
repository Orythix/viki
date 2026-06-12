"""Tests for V2 tool registry and tool base classes."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "src"))

from viki.v2.tools.base import BaseTool, ToolResult
from viki.v2.tools.registry import ToolRegistry


class TestToolResult:
    def test_success_result(self):
        r = ToolResult(success=True, data={"key": "value"})
        assert r.success is True
        assert r.data == {"key": "value"}
        assert r.error is None

    def test_failure_result(self):
        r = ToolResult(success=False, error="Something broke", error_type="runtime")
        assert r.success is False
        assert r.error == "Something broke"
        assert r.error_type == "runtime"

    def test_to_llm_observation_success(self):
        r = ToolResult(success=True, data={"msg": "ok"})
        obs = r.to_llm_observation()
        assert "succeeded" in obs
        assert "ok" in obs

    def test_to_llm_observation_failure(self):
        r = ToolResult(success=False, error="fail", error_type="test")
        obs = r.to_llm_observation()
        assert "failed" in obs
        assert "fail" in obs

    def test_to_llm_observation_with_warnings(self):
        r = ToolResult(success=True, data={}, warnings=["Disk space low"])
        obs = r.to_llm_observation()
        assert "Disk space low" in obs


class TestBaseTool:
    def test_get_tool_definition(self):
        tool = MagicMock(spec=BaseTool)
        tool.name = "test_tool"
        tool.description = "A test tool"
        tool.capabilities = ["test"]
        tool.examples = ["example 1"]
        tool.permission_tier = MagicMock()
        tool.permission_tier.name = "SAFE"
        tool.parameters = {"type": "object"}
        tool.get_tool_definition = MagicMock(
            return_value={
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "description": "A test tool",
                    "parameters": {"type": "object"},
                },
            }
        )
        definition = tool.get_tool_definition()
        assert definition["function"]["name"] == "test_tool"


class TestToolRegistry:
    def test_register_and_get(self):
        registry = ToolRegistry()
        tool = MagicMock()
        tool.name = "my_tool"
        tool.capabilities = ["cap1"]
        registry.register(tool)
        assert registry.get("my_tool") is tool

    async def test_execute_unknown_tool(self):
        registry = ToolRegistry()
        result = await registry.execute("nonexistent", {})
        assert result.success is False
        assert "Unknown" in result.error

    async def test_execute_success(self):
        registry = ToolRegistry()
        tool = MagicMock()
        tool.name = "shell"
        tool.capabilities = []
        tool.execute = AsyncMock(return_value=ToolResult(success=True, data="output"))
        registry.register(tool)

        result = await registry.execute("shell", {"cmd": "echo hi"})
        assert result.success is True
        assert result.data == "output"

    async def test_execute_exception(self):
        registry = ToolRegistry()
        tool = MagicMock()
        tool.name = "broken"
        tool.capabilities = []
        tool.execute = AsyncMock(side_effect=RuntimeError("Kaboom"))
        registry.register(tool)

        result = await registry.execute("broken", {})
        assert result.success is False
        assert "Kaboom" in result.error

    def test_list_tools(self):
        registry = ToolRegistry()
        t1 = MagicMock()
        t1.name = "a"
        t1.capabilities = []
        t2 = MagicMock()
        t2.name = "b"
        t2.capabilities = []
        registry.register(t1)
        registry.register(t2)
        assert set(registry.list_tools()) == {"a", "b"}

    def test_get_tool_definitions(self):
        registry = ToolRegistry()
        tool = MagicMock()
        tool.name = "x"
        tool.capabilities = []
        tool.get_tool_definition = MagicMock(
            return_value={"type": "function", "function": {"name": "x"}}
        )
        registry.register(tool)
        defs = registry.get_tool_definitions()
        assert len(defs) == 1
        assert defs[0]["function"]["name"] == "x"


class TestToolDiscovery:
    def test_discover_nonexistent_path(self):
        registry = ToolRegistry()
        count = registry.discover("/nonexistent/path")
        assert count == 0

    def test_discover_empty_dir(self, temp_dir):
        registry = ToolRegistry()
        count = registry.discover(str(temp_dir))
        assert count == 0

    def test_discover_single_file(self, temp_dir):
        tool_code = """
from viki.v2.tools.base import BaseTool
from viki.v2.tools.base import ToolResult

class MyTestTool(BaseTool):
    name = "my_test"
    description = "A test tool"
    capabilities = ["test"]

    async def execute(self, params, provider=None):
        return ToolResult(success=True, data="ok")
"""
        tool_file = temp_dir / "my_test_tool.py"
        tool_file.write_text(tool_code)

        registry = ToolRegistry()
        count = registry.discover(str(tool_file))
        assert count == 1
        assert registry.get("my_test") is not None

    def test_discover_directory_with_tool_py(self, temp_dir):
        tool_code = """
from viki.v2.tools.base import BaseTool
from viki.v2.tools.base import ToolResult

class DirTool(BaseTool):
    name = "dir_tool"
    description = "Tool from subdirectory"
    capabilities = []

    async def execute(self, params, provider=None):
        return ToolResult(success=True, data="ok")
"""
        subdir = temp_dir / "mytool"
        subdir.mkdir()
        (subdir / "tool.py").write_text(tool_code)

        registry = ToolRegistry()
        count = registry.discover(str(temp_dir))
        assert count == 1
        assert registry.get("dir_tool") is not None

    def test_discover_skips_abstract_classes(self, temp_dir):
        tool_code = """
from abc import ABC
from viki.v2.tools.base import BaseTool
from viki.v2.tools.base import ToolResult

class AbstractTool(BaseTool, ABC):
    pass

class ConcreteTool(BaseTool):
    name = "concrete"
    description = "Concrete tool"
    capabilities = []

    async def execute(self, params, provider=None):
        return ToolResult(success=True, data="ok")
"""
        tool_file = temp_dir / "concrete_tool.py"
        tool_file.write_text(tool_code)

        registry = ToolRegistry()
        count = registry.discover(str(tool_file))
        assert count == 1
        assert registry.get("concrete") is not None
        assert registry.get("abstracttool") is None

    def test_discover_multiple_tools_in_one_file(self, temp_dir):
        tool_code = """
from viki.v2.tools.base import BaseTool
from viki.v2.tools.base import ToolResult

class ToolOne(BaseTool):
    name = "tool_one"
    description = "First"
    capabilities = []
    async def execute(self, params, provider=None):
        return ToolResult(success=True, data="ok")

class ToolTwo(BaseTool):
    name = "tool_two"
    description = "Second"
    capabilities = []
    async def execute(self, params, provider=None):
        return ToolResult(success=True, data="ok")
"""
        tool_file = temp_dir / "multi_tool.py"
        tool_file.write_text(tool_code)

        registry = ToolRegistry()
        count = registry.discover(str(tool_file))
        assert count == 2
        assert registry.get("tool_one") is not None
        assert registry.get("tool_two") is not None

    def test_discover_prevents_duplicates(self, temp_dir):
        tool_code = """
from viki.v2.tools.base import BaseTool
from viki.v2.tools.base import ToolResult

class DupTool(BaseTool):
    name = "dup_tool"
    description = "Duplicate"
    capabilities = []
    async def execute(self, params, provider=None):
        return ToolResult(success=True, data="ok")
"""
        tool_file = temp_dir / "dup_tool.py"
        tool_file.write_text(tool_code)

        registry = ToolRegistry()
        # Discover same file twice
        count1 = registry.discover(str(tool_file))
        count2 = registry.discover(str(tool_file))
        assert count1 == 1
        assert count2 == 0
        assert len(registry.list_tools()) == 1

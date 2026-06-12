"""Tests for V2 MCP integration: config loader, client graceful degradation, and MCPTool."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "src"))


class TestMCPConfig:
    def test_load_mcp_config_no_file(self):
        from viki.v2.tools.mcp.config import load_mcp_config

        configs = load_mcp_config("/nonexistent/path.yaml")
        assert configs == []

    def test_load_mcp_config_empty_file(self, temp_dir):
        from viki.v2.tools.mcp.config import load_mcp_config

        path = temp_dir / "empty.yaml"
        path.write_text("")
        configs = load_mcp_config(str(path))
        assert configs == []

    def test_load_mcp_config_with_servers(self, temp_dir):
        from viki.v2.tools.mcp.config import load_mcp_config

        yaml_content = """
servers:
  test-server:
    transport: stdio
    command: "echo"
    args: ["hello"]
    env:
      KEY: "value"
    timeout: 30
    safety_tier: "medium"
    requires_confirmation: false
"""
        path = temp_dir / "mcp.yaml"
        path.write_text(yaml_content)
        configs = load_mcp_config(str(path))
        assert len(configs) == 1
        spec = configs[0]
        assert spec.name == "test-server"
        assert spec.transport == "stdio"
        assert spec.command == "echo"

    def test_mcp_server_spec_defaults(self):
        from viki.v2.tools.mcp.config import MCPServerSpec

        spec = MCPServerSpec(name="test")
        assert spec.timeout == 30
        assert spec.safety_tier == "medium"
        assert spec.requires_confirmation is False


class TestV2MCPClient:
    def test_client_init_no_sdk(self):
        from viki.v2.tools.mcp.client import V2MCPClient

        client = V2MCPClient()
        assert client.is_available is False

    def test_list_tools_empty_when_unavailable(self):
        from viki.v2.tools.mcp.client import V2MCPClient

        client = V2MCPClient()
        assert client.list_available_tools() == {}


class TestMCPTool:
    def test_tool_definition(self):
        from viki.v2.tools.mcp.tool import MCPTool

        tool = MCPTool(
            name="mcp_test_do_something",
            description="Does something",
            parameters={"type": "object", "properties": {}},
            server="test-server",
            tool_name="do_something",
            safety_tier="safe",
        )
        defn = tool.get_tool_definition()
        assert defn["function"]["name"] == "mcp_test_do_something"
        assert "MCP/test-server" in defn["function"]["description"]
        assert tool.capabilities == ["mcp", "test-server"]

    async def test_tool_execute_no_client(self):
        from viki.v2.tools.mcp.tool import MCPTool

        tool = MCPTool(
            name="mcp_test_foo",
            description="Foo",
            parameters={},
            server="test",
            tool_name="foo",
        )
        result = await tool.execute({})
        assert result.success is False
        assert "not bound" in result.error

    async def test_tool_execute_with_client(self):
        from viki.v2.tools.mcp.client import V2MCPClient
        from viki.v2.tools.mcp.tool import MCPTool

        client = V2MCPClient()
        tool = MCPTool(
            name="mcp_test_bar",
            description="Bar",
            parameters={},
            server="test",
            tool_name="bar",
        )
        tool.bind_client(client)
        result = await tool.execute({})
        # No SDK so it will fail with connection error, not "not bound"
        assert result.success is False
        assert "not bound" not in result.error

    def test_get_tool_definition_format(self):
        from viki.v2.tools.mcp.tool import MCPTool

        tool = MCPTool(
            name="mcp_srv_query",
            description="Run a query",
            parameters={"type": "object"},
            server="srv",
            tool_name="query",
        )
        defn = tool.get_tool_definition()
        assert defn["type"] == "function"
        assert defn["function"]["name"] == "mcp_srv_query"
        assert "MCP/srv" in defn["function"]["description"]

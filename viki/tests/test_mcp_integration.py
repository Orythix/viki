"""
P2 tier-1: MCP integration tests.

Exercises:
- yaml loading,
- graceful degradation when the `mcp` SDK isn't installed,
- MCPSkillProxy executes via the client.

We don't spawn a real MCP server; the client is monkey-patched so the proxy
roundtrip can be observed.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import unittest

from viki.integrations.mcp_client import (
    MCPClient,
    MCPSkillProxy,
    MCPServerSpec,
    attach_mcp_skills,
    load_specs_from_yaml,
)


def _run(coro):
    return asyncio.run(coro)


class _FakeRegistry:
    def __init__(self):
        self.skills = {}
    def register_skill(self, skill):
        self.skills[skill.name] = skill


class _FakeController:
    def __init__(self):
        self.skill_registry = _FakeRegistry()


class TestMcpYaml(unittest.TestCase):
    def test_load_specs_from_yaml(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            yaml_path = os.path.join(td, "mcp.yaml")
            with open(yaml_path, "w", encoding="utf-8") as f:
                f.write("servers:\n  demo:\n    command: ['echo', 'hi']\n    env:\n      X: '1'\n")
            specs = load_specs_from_yaml(yaml_path)
            self.assertEqual(len(specs), 1)
            self.assertEqual(specs[0].name, "demo")
            self.assertEqual(specs[0].command, ["echo", "hi"])
            self.assertEqual(specs[0].env, {"X": "1"})

    def test_load_missing_file_returns_empty(self):
        self.assertEqual(load_specs_from_yaml("/no/such/file.yaml"), [])


class TestMcpDegradation(unittest.TestCase):
    def test_no_sdk_returns_zero_skills(self):
        controller = _FakeController()
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            yaml_path = os.path.join(td, "mcp.yaml")
            with open(yaml_path, "w", encoding="utf-8") as f:
                f.write("servers:\n  demo:\n    command: ['echo', 'hi']\n")
            installed = _run(attach_mcp_skills(controller, mcp_config_path=yaml_path))
            self.assertEqual(installed, 0)


class TestMcpSkillProxy(unittest.TestCase):
    def test_proxy_invokes_client_call_tool(self):
        client = MCPClient()
        captured = {}

        async def fake_call_tool(server, tool, arguments):
            captured["server"] = server
            captured["tool"] = tool
            captured["arguments"] = arguments
            return {"result": "ok"}

        client.call_tool = fake_call_tool  # monkey patch
        proxy = MCPSkillProxy(client, "demo", {"name": "do_thing", "description": "x", "input_schema": {}})
        out = _run(proxy.execute({"a": 1}))
        self.assertEqual(out, "ok")
        self.assertEqual(captured["server"], "demo")
        self.assertEqual(captured["tool"], "do_thing")
        self.assertEqual(captured["arguments"], {"a": 1})

    def test_proxy_relays_error(self):
        client = MCPClient()

        async def fake_call_tool(server, tool, arguments):
            return {"error": "boom"}

        client.call_tool = fake_call_tool
        proxy = MCPSkillProxy(client, "demo", {"name": "do_thing", "description": "x", "input_schema": {}})
        out = _run(proxy.execute({}))
        self.assertIn("MCP error: boom", out)


if __name__ == "__main__":
    unittest.main()

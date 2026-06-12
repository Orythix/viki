"""Tests for V2 specialist agents and AgentManager."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "src"))

from viki.v2.agents import (
    ActionPlan,
    AgentFindings,
    AgentManager,
    AgentResult,
    SpecialistAgent,
)
from viki.v2.agents.architect_agent import ArchitectAgent
from viki.v2.agents.data_agent import DataAgent
from viki.v2.agents.developer_agent import DeveloperAgent
from viki.v2.agents.devops_agent import DevOpsAgent
from viki.v2.agents.qa_agent import QAAgent
from viki.v2.agents.research_agent import ResearchAgent
from viki.v2.agents.security_agent import SecurityAgent


class TestAgentFindings:
    def test_defaults(self):
        f = AgentFindings()
        assert f.summary == ""
        assert f.confidence == 0.0
        assert f.risks == []
        assert f.recommendations == []

    def test_full(self):
        f = AgentFindings(summary="test", confidence=0.9, risks=["r1"], recommendations=["rec1"])
        assert f.summary == "test"
        assert f.confidence == 0.9
        assert "r1" in f.risks


class TestAgentResult:
    def test_defaults(self):
        r = AgentResult()
        assert r.success is False
        assert r.output == ""

    def test_success(self):
        r = AgentResult(success=True, output="done", artifacts=["file.txt"])
        assert r.output == "done"
        assert r.artifacts == ["file.txt"]


class TestSpecialistAgents:
    async def test_architect_analyze(self, mock_llm):
        agent = ArchitectAgent(llm_client=mock_llm)
        findings = await agent.analyze({"goal": "review this repo"})
        assert findings.summary == "Test analysis"
        assert findings.confidence == 0.85

    async def test_developer_analyze(self, mock_llm):
        agent = DeveloperAgent(llm_client=mock_llm)
        findings = await agent.analyze({"goal": "fix bug"})
        assert isinstance(findings, AgentFindings)

    async def test_security_analyze(self, mock_llm):
        agent = SecurityAgent(llm_client=mock_llm)
        findings = await agent.analyze({"goal": "audit", "scan_results": ""})
        assert isinstance(findings, AgentFindings)

    async def test_qa_analyze(self, mock_llm):
        agent = QAAgent(llm_client=mock_llm)
        findings = await agent.analyze({"goal": "check quality"})
        assert isinstance(findings, AgentFindings)

    async def test_research_analyze(self, mock_llm):
        agent = ResearchAgent(llm_client=mock_llm)
        findings = await agent.analyze({"goal": "search", "query": "python"})
        assert isinstance(findings, AgentFindings)

    async def test_devops_analyze(self, mock_llm):
        agent = DevOpsAgent(llm_client=mock_llm)
        findings = await agent.analyze({"goal": "check infra"})
        assert isinstance(findings, AgentFindings)

    async def test_data_analyze(self, mock_llm):
        agent = DataAgent(llm_client=mock_llm)
        findings = await agent.analyze({"goal": "analyze data"})
        assert isinstance(findings, AgentFindings)

    async def test_agent_execute(self, mock_llm, mock_registry):
        agent = ArchitectAgent(llm_client=mock_llm, tool_registry=mock_registry)
        plan = ActionPlan(steps=[{"tool": "shell", "params": {"cmd": "echo hi"}}])
        result = await agent.execute(plan)
        assert result.success is True


class TestAgentManager:
    def test_init_creates_all_agents(self, mock_llm):
        mgr = AgentManager(llm_client=mock_llm)
        agents = mgr.list_agents()
        assert "architect" in agents
        assert "developer" in agents
        assert "security" in agents
        assert "research" in agents
        assert "devops" in agents
        assert "data" in agents
        assert "qa" in agents
        assert len(agents) == 7

    def test_get_agent(self, mock_llm):
        mgr = AgentManager(llm_client=mock_llm)
        agent = mgr.get_agent("architect")
        assert agent is not None
        assert agent.name == "architect"

    def test_get_agent_unknown(self, mock_llm):
        mgr = AgentManager(llm_client=mock_llm)
        assert mgr.get_agent("nonexistent") is None

    def test_register_agent(self, mock_llm):
        mgr = AgentManager(llm_client=mock_llm)
        custom = MagicMock(spec=SpecialistAgent)
        custom.name = "custom"
        mgr.register_agent("custom", custom)
        assert mgr.get_agent("custom") is custom

    async def test_analyze(self, mock_llm):
        mgr = AgentManager(llm_client=mock_llm)
        findings = await mgr.analyze("architect", {"goal": "test"})
        assert isinstance(findings, AgentFindings)

    async def test_analyze_unknown_agent(self, mock_llm):
        mgr = AgentManager(llm_client=mock_llm)
        findings = await mgr.analyze("ghost", {"goal": "test"})
        assert "not available" in findings.summary

    async def test_dispatch_all(self, mock_llm):
        mgr = AgentManager(llm_client=mock_llm)
        report = await mgr.dispatch_all("review this")
        assert len(report.results) == 7  # one per agent
        assert report.goal == "review this"

    async def test_dispatch_all_with_errors(self, mock_llm):
        mock_llm.structured_output.side_effect = RuntimeError("fail")
        mgr = AgentManager(llm_client=mock_llm)
        report = await mgr.dispatch_all("test")
        # Errors are caught gracefully and placed in findings, not errors dict
        assert len(report.results) == 7
        for _, findings in report.results.items():
            assert "failed" in findings.summary.lower()

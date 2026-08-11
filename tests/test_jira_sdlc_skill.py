"""Unit tests for JiraSDLCWorkflowSkill."""

from __future__ import annotations

import json

import pytest

from viki.skills.builtins.jira_sdlc_skill import JiraSDLCWorkflowSkill


@pytest.mark.asyncio
async def test_jira_sdlc_skill_parse_ticket():
    skill = JiraSDLCWorkflowSkill()
    res_str = await skill.execute(
        {
            "action": "parse_jira_ticket",
            "ticket_id": "FE-404",
            "summary": "Implement modern responsive user dashboard",
        }
    )
    res = json.loads(res_str)
    assert res["ticket_id"] == "FE-404"
    assert len(res["subtasks"]) == 4


@pytest.mark.asyncio
async def test_jira_sdlc_skill_design_spec():
    skill = JiraSDLCWorkflowSkill()
    spec = await skill.execute(
        {
            "action": "generate_design_spec",
            "ticket_id": "FE-404",
            "summary": "User dashboard UI",
        }
    )
    assert "Design System Spec" in spec
    assert "FE-404" in spec

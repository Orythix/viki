from unittest.mock import AsyncMock, MagicMock

import pytest
from viki.skills.builtins.market_explorer_skill import MarketExplorerSkill


class MockSkill:
    def __init__(self, return_val):
        self.execute = AsyncMock(return_value=return_val)


class MockController:
    def __init__(self):
        self.skill_registry = MagicMock()
        self.skills = {}
        self.skill_registry.get_skill.side_effect = lambda name: self.skills.get(name)


@pytest.mark.asyncio
async def test_market_explorer_synergy():
    ctrl = MockController()

    # Mock skills
    ctrl.skills["research"] = MockSkill("Search Data: AI Trends")
    ctrl.skills["manus"] = MockSkill("Analysis Report: Growing")
    ctrl.skills["filesystem_skill"] = MockSkill("File Saved")

    skill = MarketExplorerSkill(ctrl)

    result = await skill.execute({"topic": "AI Trends"})

    # Verify orchestration
    assert "COMPLETED" in result
    assert "market_report.md" in result

    # Verify call sequence
    ctrl.skills["research"].execute.assert_called_once()
    ctrl.skills["manus"].execute.assert_called_once()
    ctrl.skills["filesystem_skill"].execute.assert_called_once()

    # Check if analysis received search data
    call_args = ctrl.skills["manus"].execute.call_args[0][0]
    assert "Search Data: AI Trends" in call_args["task"]

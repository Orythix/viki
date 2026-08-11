"""Unit tests for MCTS Tree Search reasoning engine."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from viki.core.react_loop import MCTSNode, run_mcts_tree_search
from viki.core.schema import ActionCall


def test_mcts_node_ucb1_and_selection():
    root = MCTSNode()
    root.visits = 10

    child1 = MCTSNode(action=ActionCall(skill_name="test_skill_1"), parent=root)
    child1.visits = 5
    child1.score = 15.0

    child2 = MCTSNode(action=ActionCall(skill_name="test_skill_2"), parent=root)
    child2.visits = 5
    child2.score = 25.0

    root.children = [child1, child2]

    best = root.select_best_child()
    assert best is not None
    assert best.action is not None
    assert best.action.skill_name == "test_skill_2"


@pytest.mark.asyncio
async def test_run_mcts_tree_search_execution():
    controller = MagicMock()
    controller.capabilities.check_permission.return_value = MagicMock(allowed=True)
    controller._execute_skill = AsyncMock(return_value=("Success output from trial", None, 0.05))

    candidate_actions = [
        ActionCall(skill_name="skill_a", parameters={"query": "test"}),
        ActionCall(skill_name="skill_b", parameters={"query": "test"}),
    ]

    best_action, score = await run_mcts_tree_search(
        controller=controller,
        user_input="test query",
        candidate_actions=candidate_actions,
        budget={},
    )

    assert best_action is not None
    assert score > 0

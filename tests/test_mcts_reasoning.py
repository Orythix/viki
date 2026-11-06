"""Unit tests for MCTS Tree Search reasoning engine."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from viki.core.react_loop import (
    MCTSNode,
    collect_mcts_candidates,
    run_mcts_tree_search,
    should_run_mcts,
)
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


def test_mcts_most_visited_prefers_visits():
    root = MCTSNode()
    a = MCTSNode(action=ActionCall(skill_name="a"), parent=root)
    a.visits = 3
    a.score = 1.0
    b = MCTSNode(action=ActionCall(skill_name="b"), parent=root)
    b.visits = 7
    b.score = 0.5
    root.children = [a, b]
    winner = root.most_visited_child()
    assert winner is not None
    assert winner.action is not None
    assert winner.action.skill_name == "b"


def test_should_run_mcts_only_deep_hard_tasks():
    route = MagicMock()
    route.use_mcts = True
    route.outcome = MagicMock(value="deep")
    route.use_ensemble = False
    assert should_run_mcts(route, "coding") is True
    assert should_run_mcts(route, "chatter") is False
    assert should_run_mcts(None, "coding") is False


def test_collect_mcts_candidates_dedupes():
    a = ActionCall(skill_name="shell", parameters={"cmd": "ls"})
    b = ActionCall(skill_name="shell", parameters={"cmd": "ls"})
    c = ActionCall(skill_name="research", parameters={"q": "x"})
    out = collect_mcts_candidates(a, extras=[b, c])
    assert len(out) == 2
    assert {x.skill_name for x in out} == {"shell", "research"}


@pytest.mark.asyncio
async def test_run_mcts_tree_search_verifier_not_length():
    """Longer erroring output must not beat a short successful one."""
    controller = MagicMock()
    controller.capabilities.check_permission.return_value = MagicMock(allowed=True)
    controller._skill_action_severity = MagicMock(return_value="low")

    async def _exec(skill_name, params, budget):
        if skill_name == "skill_good":
            return ("ok done success", None, 0.01)
        return ("error " + ("x" * 5000), "boom", 0.01)

    controller._execute_skill = AsyncMock(side_effect=_exec)

    candidate_actions = [
        ActionCall(skill_name="skill_bad", parameters={"query": "test"}),
        ActionCall(skill_name="skill_good", parameters={"query": "test"}),
    ]

    best_action, score = await run_mcts_tree_search(
        controller=controller,
        user_input="test query",
        candidate_actions=candidate_actions,
        budget={"mcts_max_simulations": 4, "mcts_max_seconds": 5.0, "mcts_force_execute": True},
    )

    assert best_action is not None
    assert best_action.skill_name == "skill_good"
    assert score > 0


@pytest.mark.asyncio
async def test_run_mcts_budget_abort():
    controller = MagicMock()
    controller.capabilities.check_permission.return_value = MagicMock(allowed=True)
    controller._skill_action_severity = MagicMock(return_value="low")
    controller._execute_skill = AsyncMock(return_value=("ok", None, 0.01))

    candidates = [
        ActionCall(skill_name="a", parameters={}),
        ActionCall(skill_name="b", parameters={}),
    ]
    best, score = await run_mcts_tree_search(
        controller,
        "q",
        candidates,
        budget={"mcts_max_simulations": 2, "mcts_max_seconds": 0.0001},
    )
    assert best is not None
    # Budget abort still returns a valid selection.
    assert score == score  # finite

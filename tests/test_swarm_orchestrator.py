"""Unit tests for SwarmOrchestrator and Swarm DAG state."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from viki.core.swarm_orchestrator import SwarmOrchestrator


@pytest.mark.asyncio
async def test_swarm_orchestrator_lifecycle():
    controller = MagicMock()
    so = SwarmOrchestrator(controller)

    swarm_id = so.create_swarm("Build a weather dashboard microservice")
    assert swarm_id.startswith("swarm_")

    initial_state = so.get_swarm_dag_state(swarm_id)
    assert initial_state["status"] == "initialized"
    assert len(initial_state["nodes"]) == 3

    final_state = await so.execute_swarm(swarm_id)
    assert final_state["status"] == "completed"
    assert all(n["status"] == "completed" for n in final_state["nodes"])

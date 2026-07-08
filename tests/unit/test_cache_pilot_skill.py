import shutil
import tempfile

import pytest

from viki.core.utils.semantic_cache import SemanticCache
from viki.skills.builtins.cache_pilot_skill import CachePilotSkill


class MockController:
    def __init__(self, data_dir):
        self.settings = {"system": {"data_dir": data_dir}}
        self.router = type("obj", (object,), {"cache": SemanticCache(data_dir)})


@pytest.fixture
def temp_viki():
    data_dir = tempfile.mkdtemp()
    ctrl = MockController(data_dir)
    yield ctrl
    shutil.rmtree(data_dir)


@pytest.mark.asyncio
async def test_cache_pilot_stats(temp_viki):
    skill = CachePilotSkill(temp_viki)
    # Warm it first
    await skill.execute({"action": "warm", "query": "test query", "response": "test response"})

    result = await skill.execute({"action": "stats"})
    assert "Total Entries: 1" in result
    assert "test query" in result


@pytest.mark.asyncio
async def test_cache_pilot_list(temp_viki):
    skill = CachePilotSkill(temp_viki)
    await skill.execute({"action": "warm", "query": "query 1", "response": "resp 1"})
    await skill.execute({"action": "warm", "query": "query 2", "response": "resp 2"})

    result = await skill.execute({"action": "list", "limit": 5})
    assert "query 1" in result
    assert "query 2" in result


@pytest.mark.asyncio
async def test_cache_pilot_prune(temp_viki):
    skill = CachePilotSkill(temp_viki)
    await skill.execute({"action": "warm", "query": "to delete", "response": "gone"})

    # Prune specific
    result = await skill.execute({"action": "prune", "query": "to delete"})
    assert "removed" in result

    stats = await skill.execute({"action": "stats"})
    assert "Total Entries: 0" in result or "Total Entries: 0" in stats


@pytest.mark.asyncio
async def test_cache_pilot_clear_all(temp_viki):
    skill = CachePilotSkill(temp_viki)
    await skill.execute({"action": "warm", "query": "q1", "response": "r1"})
    await skill.execute({"action": "warm", "query": "q2", "response": "r2"})

    # Clear all
    result = await skill.execute({"action": "prune"})
    assert "wiped" in result

    stats = await skill.execute({"action": "stats"})
    assert "Total Entries: 0" in stats

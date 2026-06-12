"""Tests for V2 memory modules."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "src"))


class TestSessionMemory:
    def test_add_turn_and_get_context(self):
        from viki.v2.memory import SessionMemory

        mem = SessionMemory()
        mem.add_turn(user="hello", assistant="hi")
        context = mem.get_context()
        assert len(context) > 0

    def test_set_and_get_state(self):
        from viki.v2.memory import SessionMemory

        mem = SessionMemory()
        mem.set_state("key1", {"value": 42})
        assert mem.get_state("key1") == {"value": 42}

    def test_get_state_default(self):
        from viki.v2.memory import SessionMemory

        mem = SessionMemory()
        assert mem.get_state("nonexistent", "fallback") == "fallback"

    def test_pending_actions(self):
        from viki.v2.memory import SessionMemory

        mem = SessionMemory()
        mem.add_pending_action({"tool": "shell", "params": {}})
        mem.clear_pending()


class TestProjectMemory:
    @pytest.mark.asyncio
    async def test_set_and_get_active_project(self):
        from viki.v2.memory import ProjectMemory

        mem = ProjectMemory(":memory:")
        await mem.set_active_project("/some/path")
        info = await mem.get_active_project()
        assert info is not None
        assert info.path.endswith("some/path") or info.path.endswith("some\\path")

    @pytest.mark.asyncio
    async def test_get_active_project_none(self):
        from viki.v2.memory import ProjectMemory

        mem = ProjectMemory(":memory:")
        assert await mem.get_active_project() is None

    @pytest.mark.asyncio
    async def test_record_decision(self):
        from viki.v2.memory import ProjectMemory

        mem = ProjectMemory(":memory:")
        await mem.set_active_project("/proj")
        await mem.record_decision("Use FastAPI", "Best for async", "High throughput needed")
        decisions = await mem.get_recent_decisions()
        assert len(decisions) >= 1

    @pytest.mark.asyncio
    async def test_context(self):
        from viki.v2.memory import ProjectMemory

        mem = ProjectMemory(":memory:")
        await mem.set_context("theme", "dark")
        assert await mem.get_context("theme") == "dark"

    @pytest.mark.asyncio
    async def test_tasks(self):
        from viki.v2.memory import ProjectMemory

        mem = ProjectMemory(":memory:")
        tid = await mem.add_task("Fix bug", "Critical issue")
        assert tid > 0
        tasks = await mem.get_tasks()
        assert len(tasks) == 1


class TestLongTermMemory:
    @pytest.mark.asyncio
    async def test_set_and_get_preference(self):
        from viki.v2.memory import LongTermMemory

        mem = LongTermMemory(":memory:")
        await mem.set_preference("language", "python")
        assert await mem.get_preference("language") == "python"

    @pytest.mark.asyncio
    async def test_get_preference_missing(self):
        from viki.v2.memory import LongTermMemory

        mem = LongTermMemory(":memory:")
        assert await mem.get_preference("nonexistent") is None

    @pytest.mark.asyncio
    async def test_all_preferences(self):
        from viki.v2.memory import LongTermMemory

        mem = LongTermMemory(":memory:")
        await mem.set_preference("a", "1")
        await mem.set_preference("b", "2")
        prefs = await mem.get_all_preferences()
        assert len(prefs) >= 2

    @pytest.mark.asyncio
    async def test_learn_and_recall_pattern(self):
        from viki.v2.memory import LongTermMemory

        mem = LongTermMemory(":memory:")
        await mem.learn_pattern("handle error", "use try/except", success=True)
        patterns = await mem.recall_patterns("handle error")
        assert len(patterns) >= 1

    @pytest.mark.asyncio
    async def test_knowledge(self):
        from viki.v2.memory import LongTermMemory

        mem = LongTermMemory(":memory:")
        await mem.store_knowledge("Python", "Duck-typed language", "docs")
        results = await mem.retrieve_knowledge("Python")
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_tool_stats(self):
        from viki.v2.memory import LongTermMemory

        mem = LongTermMemory(":memory:")
        await mem.log_tool_usage("shell", {"cmd": "ls"}, True, 10.5)
        stats = await mem.get_tool_stats()
        assert len(stats) >= 1

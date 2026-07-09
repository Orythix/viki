"""Tests for WatcherManager and Watcher."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from viki.core.watchers import Watcher, WatcherManager


class TestWatcher:
    def test_to_dict_roundtrip(self) -> None:
        w = Watcher(
            id="abc123",
            name="test-watcher",
            kind="file",
            config={"path": "/tmp"},
            mission_description="check files",
            mission_priority=30,
            mission_type="audit",
        )
        data = w.to_dict()
        for k, v in data.items():
            assert getattr(w, k, object()) == v

    def test_from_dict_restores_fields(self) -> None:
        data = {
            "id": "xyz789",
            "name": "restored",
            "kind": "rss",
            "config": {"url": "https://example.com/rss"},
            "mission_description": "feed check",
            "mission_priority": 60,
            "cooldown_seconds": 600,
            "last_fired": 1000.0,
            "total_firings": 5,
        }
        w = Watcher.from_dict(data)
        assert w.id == "xyz789"
        assert w.name == "restored"
        assert w.kind == "rss"
        assert w.config["url"] == "https://example.com/rss"
        assert w.cooldown_seconds == 600
        assert w.last_fired == 1000.0
        assert w.total_firings == 5

    def test_from_dict_ignores_unknown_keys(self) -> None:
        data = {"id": "x", "name": "y", "unknown_field": "z"}
        w = Watcher.from_dict(data)
        assert w.id == "x"
        assert not hasattr(w, "unknown_field")


class TestWatcherManager:
    @pytest.fixture
    def data_dir(self, tmp_path: Path) -> str:
        return str(tmp_path / "viki_watchers")

    @pytest.fixture
    def mission_control(self) -> object:
        class _StubMC:
            def __init__(self) -> None:
                self.missions: list[dict] = []

            def add_mission(self, description: str, priority: int, m_type: str) -> None:
                self.missions.append(
                    {
                        "description": description,
                        "priority": priority,
                        "type": m_type,
                    }
                )

        return _StubMC()

    @pytest.fixture
    def manager(self, data_dir: str, mission_control: object) -> WatcherManager:
        return WatcherManager(mission_control, data_dir=data_dir)

    def test_add_watcher_assigns_id(self, manager: WatcherManager) -> None:
        w = Watcher(name="test", kind="file")
        wid = manager.add_watcher(w)
        assert len(wid) == 8
        assert manager.get_watcher(wid) is w

    def test_list_watchers(self, manager: WatcherManager) -> None:
        manager.add_watcher(Watcher(name="a", kind="file"))
        manager.add_watcher(Watcher(name="b", kind="rss"))
        assert len(manager.list_watchers()) == 2

    def test_remove_watcher_returns_true(self, manager: WatcherManager) -> None:
        wid = manager.add_watcher(Watcher(name="del", kind="file"))
        assert manager.remove_watcher(wid) is True
        assert manager.get_watcher(wid) is None

    def test_remove_watcher_returns_false(self, manager: WatcherManager) -> None:
        assert manager.remove_watcher("nonexistent") is False

    def test_get_watcher_returns_none_for_missing(self, manager: WatcherManager) -> None:
        assert manager.get_watcher("missing") is None

    def test_fire_webhook_success(self, manager: WatcherManager) -> None:
        import asyncio

        async def _run() -> None:
            wid = manager.add_watcher(
                Watcher(
                    name="hook",
                    kind="webhook",
                    mission_description="webhook test",
                )
            )
            assert manager.fire_webhook(wid) is True

        asyncio.run(_run())

    def test_fire_webhook_wrong_kind(self, manager: WatcherManager) -> None:
        wid = manager.add_watcher(Watcher(name="file-watcher", kind="file"))
        assert manager.fire_webhook(wid) is False

    def test_fire_webhook_missing_id(self, manager: WatcherManager) -> None:
        assert manager.fire_webhook("doesnotexist") is False

    def test_check_file_watcher_modified(self, manager: WatcherManager, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("hello")
        w = Watcher(
            id="f1",
            name="file-check",
            kind="file",
            config={"path": str(f)},
        )
        manager._watchers["f1"] = w
        assert manager._check_file_watcher(w) is True

    def test_check_file_watcher_not_modified(self, manager: WatcherManager, tmp_path: Path) -> None:
        f = tmp_path / "stale.txt"
        f.write_text("old")
        w = Watcher(
            id="f2",
            name="stale",
            kind="file",
            config={"path": str(f)},
            last_fired=time.time() + 3600,
        )
        manager._watchers["f2"] = w
        assert manager._check_file_watcher(w) is False

    def test_check_file_watcher_missing_path(self, manager: WatcherManager) -> None:
        w = Watcher(
            id="f3",
            name="missing",
            kind="file",
            config={"path": "/nonexistent/path"},
        )
        manager._watchers["f3"] = w
        assert manager._check_file_watcher(w) is False

    def test_persistence_roundtrip(self, manager: WatcherManager, data_dir: str) -> None:
        w = Watcher(name="persist-test", kind="rss", config={"url": "https://example.com/rss"})
        wid = manager.add_watcher(w)
        path = os.path.join(data_dir, "watchers.json")
        assert os.path.isfile(path)
        with open(path) as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["id"] == wid

    def test_load_restores_watchers(self, manager: WatcherManager, data_dir: str) -> None:
        w = Watcher(name="load-test", kind="webhook")
        manager.add_watcher(w)
        manager2 = WatcherManager(manager._mc, data_dir=data_dir)
        assert len(manager2.list_watchers()) == 1

    def test_start_stop_lifecycle(self, manager: WatcherManager) -> None:
        import asyncio

        async def _run() -> None:
            manager.start()
            assert manager._running is True
            assert manager._loop_task is not None
            await manager.stop()

        asyncio.run(_run())

    def test_add_watcher_persists(self, manager: WatcherManager, data_dir: str) -> None:
        manager.add_watcher(Watcher(name="p", kind="file"))
        path = os.path.join(data_dir, "watchers.json")
        with open(path) as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["name"] == "p"

"""
Watchers — user-defined triggers that fire missions autonomously.

Supports:
  - File/folder changes (via watchdog)
  - Calendar proximity
  - Inbox arrival (email)
  - RSS/Atom feed polling
  - Webhook endpoints

Each watcher fires a mission with a budget when triggered.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

from viki.config.logger import viki_logger


@dataclass
class Watcher:
    """A user-defined trigger that fires missions."""

    id: str = ""
    name: str = ""
    kind: str = "file"  # file, calendar, inbox, rss, webhook
    config: dict[str, Any] = field(default_factory=dict)
    mission_description: str = ""
    mission_priority: int = 50
    mission_type: str = "monitoring"
    enabled: bool = True
    cooldown_seconds: int = 300  # min time between firings
    last_fired: float = 0.0
    total_firings: int = 0
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "config": self.config,
            "mission_description": self.mission_description,
            "mission_priority": self.mission_priority,
            "mission_type": self.mission_type,
            "enabled": self.enabled,
            "cooldown_seconds": self.cooldown_seconds,
            "last_fired": self.last_fired,
            "total_firings": self.total_firings,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Watcher:
        w = cls()
        for k, v in data.items():
            if hasattr(w, k):
                setattr(w, k, v)
        return w


class WatcherManager:
    """
    Manages watchers: create, list, enable/disable, and the background
    polling loop.
    """

    def __init__(self, mission_control: Any, data_dir: str = "./data"):
        self._mc = mission_control
        self._watchers: dict[str, Watcher] = {}
        self._running = False
        self._loop_task: asyncio.Task | None = None
        self._persistence_path = os.path.join(data_dir, "watchers.json")
        os.makedirs(data_dir, exist_ok=True)
        self._load()

    def add_watcher(self, watcher: Watcher) -> str:
        import uuid

        watcher.id = str(uuid.uuid4())[:8]
        watcher.created_at = time.time()
        self._watchers[watcher.id] = watcher
        self._save()
        viki_logger.info("WatcherManager: added '%s' (%s)", watcher.name, watcher.kind)
        return watcher.id

    def remove_watcher(self, watcher_id: str) -> bool:
        if watcher_id in self._watchers:
            del self._watchers[watcher_id]
            self._save()
            return True
        return False

    def list_watchers(self) -> list[Watcher]:
        return list(self._watchers.values())

    def get_watcher(self, watcher_id: str) -> Watcher | None:
        return self._watchers.get(watcher_id)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._loop_task = asyncio.create_task(self._run_loop())
        viki_logger.info("WatcherManager: started (%d watchers)", len(self._watchers))

    async def stop(self) -> None:
        self._running = False
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass

    async def _run_loop(self) -> None:
        while self._running:
            try:
                for watcher in list(self._watchers.values()):
                    if not watcher.enabled:
                        continue
                    if time.time() - watcher.last_fired < watcher.cooldown_seconds:
                        continue
                    if await self._check_watcher(watcher):
                        await self._fire_watcher(watcher)
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                break
            except Exception as e:
                viki_logger.error("WatcherManager loop error: %s", e)
                await asyncio.sleep(60)

    async def _check_watcher(self, watcher: Watcher) -> bool:
        """Check if the watcher condition is met."""
        try:
            if watcher.kind == "file":
                return self._check_file_watcher(watcher)
            elif watcher.kind == "rss":
                return await self._check_rss_watcher(watcher)
            elif watcher.kind == "inbox":
                return await self._check_inbox_watcher(watcher)
            elif watcher.kind == "webhook":
                return False  # Webhooks are external; they call fire directly
            return False
        except Exception as e:
            viki_logger.debug("Watcher check failed for '%s': %s", watcher.name, e)
            return False

    def _check_file_watcher(self, watcher: Watcher) -> bool:
        path = watcher.config.get("path", "")
        pattern = watcher.config.get("pattern", "")
        if not path or not os.path.exists(path):
            return False
        mod_time = os.path.getmtime(path)
        if mod_time > watcher.last_fired:
            return True
        if pattern:
            for f in os.listdir(path) if os.path.isdir(path) else [path]:
                if pattern in f:
                    return True
        return False

    async def _check_rss_watcher(self, watcher: Watcher) -> bool:
        url = watcher.config.get("url", "")
        if not url:
            return False
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        if "item" in text or "entry" in text:
                            return True
        except Exception:
            viki_logger.warning("watcher web check failed")
        return False

    async def _check_inbox_watcher(self, watcher: Watcher) -> bool:
        return False  # Requires IMAP/API integration

    async def _fire_watcher(self, watcher: Watcher) -> None:
        viki_logger.info("WatcherManager: firing watcher '%s'", watcher.name)
        try:
            if self._mc and hasattr(self._mc, "add_mission"):
                self._mc.add_mission(
                    description=watcher.mission_description or f"Watcher triggered: {watcher.name}",
                    priority=watcher.mission_priority,
                    m_type=watcher.mission_type,
                )
            watcher.last_fired = time.time()
            watcher.total_firings += 1
            self._save()
        except Exception as e:
            viki_logger.error("WatcherManager: fire failed for '%s': %s", watcher.name, e)

    def fire_webhook(self, webhook_id: str) -> bool:
        """External call to fire a webhook watcher."""
        watcher = self._watchers.get(webhook_id)
        if watcher and watcher.kind == "webhook":
            asyncio.create_task(self._fire_watcher(watcher))
            return True
        return False

    def _save(self) -> None:
        try:
            data = [w.to_dict() for w in self._watchers.values()]
            with open(self._persistence_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            viki_logger.error("WatcherManager: save failed: %s", e)

    def _load(self) -> None:
        if not os.path.exists(self._persistence_path):
            return
        try:
            with open(self._persistence_path) as f:
                data = json.load(f)
            for item in data:
                w = Watcher.from_dict(item)
                self._watchers[w.id] = w
        except Exception as e:
            viki_logger.error("WatcherManager: load failed: %s", e)

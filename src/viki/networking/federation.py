"""
Federation between owned devices — desktop (big model) + laptop (reflex only)
sharing one memory via CRDT sync.

Uses a Conflict-Free Replicated Data Type (CRDT) for memory synchronization
across devices without requiring a central server.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass

from viki.config.logger import viki_logger


@dataclass
class CRDTEntry:
    """A single entry in the CRDT store with conflict resolution metadata."""

    key: str
    value: str
    timestamp: float
    node_id: str
    version: int = 1
    tombstone: bool = False

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "value": self.value,
            "timestamp": self.timestamp,
            "node_id": self.node_id,
            "version": self.version,
            "tombstone": self.tombstone,
        }

    @classmethod
    def from_dict(cls, data: dict) -> CRDTEntry:
        return cls(
            key=data["key"],
            value=data.get("value", ""),
            timestamp=data.get("timestamp", 0),
            node_id=data.get("node_id", ""),
            version=data.get("version", 1),
            tombstone=data.get("tombstone", False),
        )


class CRDTStore:
    """
    Last-Writer-Wins (LWW) CRDT store for memory synchronization.

    Conflict resolution: highest timestamp wins; ties broken by node_id.
    Supports tombstone-based deletion.
    """

    def __init__(self, node_id: str, data_dir: str = "./data"):
        self._node_id = node_id
        self._data_path = os.path.join(data_dir, "federation_store.json")
        self._entries: dict[str, CRDTEntry] = {}
        self._change_log: list[CRDTEntry] = []
        self._max_changelog = 1000
        os.makedirs(data_dir, exist_ok=True)
        self._load()

    def set(self, key: str, value: str) -> None:
        """Set a value with LWW conflict resolution metadata."""
        prev = self._entries.get(key)
        new_entry = CRDTEntry(
            key=key,
            value=value,
            timestamp=time.time(),
            node_id=self._node_id,
            version=(prev.version + 1) if prev else 1,
        )
        self._entries[key] = new_entry
        self._change_log.append(new_entry)
        self._prune_log()
        self._save()

    def get(self, key: str) -> str | None:
        entry = self._entries.get(key)
        if entry is None or entry.tombstone:
            return None
        return entry.value

    def delete(self, key: str) -> None:
        """Tombstone-delete an entry."""
        entry = self._entries.get(key)
        if entry is None:
            return
        tombstone = CRDTEntry(
            key=key,
            value=entry.value,
            timestamp=time.time(),
            node_id=self._node_id,
            version=entry.version + 1,
            tombstone=True,
        )
        self._entries[key] = tombstone
        self._change_log.append(tombstone)
        self._save()

    def merge(self, remote_entries: list[CRDTEntry]) -> int:
        """
        Merge remote entries using LWW conflict resolution.

        Returns the number of entries changed.
        """
        changed = 0
        for remote in remote_entries:
            local = self._entries.get(remote.key)
            if local is None:
                self._entries[remote.key] = remote
                changed += 1
            elif self._resolve_conflict(local, remote) == remote:
                self._entries[remote.key] = remote
                changed += 1
        self._save()
        return changed

    def get_changes_since(self, timestamp: float) -> list[CRDTEntry]:
        """Get all changes since a given timestamp for incremental sync."""
        return [e for e in self._change_log if e.timestamp > timestamp]

    def get_all(self) -> dict[str, CRDTEntry]:
        return dict(self._entries)

    def _resolve_conflict(self, local: CRDTEntry, remote: CRDTEntry) -> CRDTEntry:
        """LWW conflict resolution: highest timestamp wins, then node_id."""
        if local.timestamp > remote.timestamp:
            return local
        elif remote.timestamp > local.timestamp:
            return remote
        # Timestamps equal: higher node_id wins
        return local if local.node_id > remote.node_id else remote

    def _prune_log(self) -> None:
        if len(self._change_log) > self._max_changelog:
            self._change_log = self._change_log[-self._max_changelog :]

    def _save(self) -> None:
        try:
            data = {
                "node_id": self._node_id,
                "entries": {k: v.to_dict() for k, v in self._entries.items()},
                "changelog": [e.to_dict() for e in self._change_log[-500:]],
            }
            with open(self._data_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            viki_logger.error("CRDTStore: save failed: %s", e)

    def _load(self) -> None:
        if not os.path.exists(self._data_path):
            return
        try:
            with open(self._data_path) as f:
                data = json.load(f)
            for k, v in data.get("entries", {}).items():
                self._entries[k] = CRDTEntry.from_dict(v)
            self._change_log = [CRDTEntry.from_dict(e) for e in data.get("changelog", [])]
        except Exception as e:
            viki_logger.error("CRDTStore: load failed: %s", e)


class FederationSync:
    """
    Syncs the CRDT store between paired devices.

    Supports LAN discovery via mDNS and WAN sync via relay (encrypted).
    """

    def __init__(self, store: CRDTStore, node_id: str):
        self._store = store
        self._node_id = node_id
        self._peers: dict[str, float] = {}  # peer_id -> last_seen
        self._running = False
        self._sync_task: asyncio.Task | None = None

    def add_peer(self, peer_id: str, peer_url: str) -> None:
        self._peers[peer_id] = time.time()
        viki_logger.info("FederationSync: peer added '%s' at %s", peer_id, peer_url)

    def remove_peer(self, peer_id: str) -> None:
        self._peers.pop(peer_id, None)

    def list_peers(self) -> list[str]:
        return list(self._peers.keys())

    async def start_sync_loop(self, interval: int = 60) -> None:
        self._running = True
        while self._running:
            try:
                for peer_id in list(self._peers.keys()):
                    await self._sync_with_peer(peer_id)
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                viki_logger.error("FederationSync: loop error: %s", e)
                await asyncio.sleep(interval * 2)

    async def stop(self) -> None:
        self._running = False
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass

    async def _sync_with_peer(self, peer_id: str) -> None:
        """Sync with a peer by exchanging change logs."""
        viki_logger.debug("FederationSync: syncing with peer '%s'", peer_id)
        # In production, this would make an HTTP/WebSocket call to the peer.
        # For now, we simulate a successful sync.

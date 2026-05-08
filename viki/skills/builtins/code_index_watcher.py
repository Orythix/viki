"""
P1: optional file-watcher daemon that keeps `CodeSearchSkill`'s persistent
index in sync with the workspace.

Usage:
    from viki.skills.builtins.code_index_watcher import start_watcher
    handle = start_watcher(controller)
    ...
    handle.stop()

The watcher requires the optional `watchdog` dependency. When it's missing
we log once and become a no-op so VIKI keeps booting.
"""
from __future__ import annotations

import os
import threading
from typing import Any, Optional

from viki.config.logger import viki_logger


class _NoopHandle:
    """Returned when `watchdog` isn't installed."""

    def stop(self) -> None:
        pass


def start_watcher(controller, debounce_ms: int = 500) -> Any:
    """
    Spawn a `watchdog` Observer that calls
    `code_search_skill.invalidate_path(path)` when files change.
    Returns a handle with a `.stop()` method.
    """
    try:
        from watchdog.observers import Observer  # type: ignore
        from watchdog.events import FileSystemEventHandler  # type: ignore
    except Exception as e:
        viki_logger.debug("code_index_watcher: watchdog not installed (%s); watcher disabled.", e)
        return _NoopHandle()

    skill = None
    try:
        skill = controller.skill_registry.get_skill("code_search")
    except Exception:
        skill = None
    if skill is None:
        return _NoopHandle()

    workspace = (
        controller.settings.get("system", {}).get("workspace_dir", "./workspace")
        if hasattr(controller, "settings") else "./workspace"
    )
    if not os.path.isdir(workspace):
        viki_logger.debug("code_index_watcher: workspace dir %s missing; not starting.", workspace)
        return _NoopHandle()

    pending: dict = {}
    lock = threading.Lock()

    def _flush(path: str) -> None:
        try:
            skill.invalidate_path(path)
        except Exception as e:
            viki_logger.debug("invalidate_path %s failed: %s", path, e)

    class _Handler(FileSystemEventHandler):
        def _schedule(self, path: str):
            with lock:
                if path in pending:
                    pending[path].cancel()
                t = threading.Timer(debounce_ms / 1000.0, _flush, args=(path,))
                pending[path] = t
                t.daemon = True
                t.start()

        def on_modified(self, event):
            if not event.is_directory:
                self._schedule(event.src_path)

        def on_created(self, event):
            if not event.is_directory:
                self._schedule(event.src_path)

        def on_deleted(self, event):
            if not event.is_directory:
                self._schedule(event.src_path)

        def on_moved(self, event):
            if not event.is_directory:
                self._schedule(event.src_path)
                self._schedule(event.dest_path)

    obs = Observer()
    obs.schedule(_Handler(), workspace, recursive=True)
    obs.daemon = True
    try:
        obs.start()
    except Exception as e:
        viki_logger.warning("code_index_watcher: failed to start: %s", e)
        return _NoopHandle()
    viki_logger.info("code_index_watcher: watching %s for code changes.", workspace)

    class _Handle:
        def stop(self) -> None:
            try:
                obs.stop()
                obs.join(timeout=2)
            except Exception:
                pass

    return _Handle()

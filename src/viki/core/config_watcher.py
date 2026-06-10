import os
import time
import logging
from typing import Callable, Optional, Set

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent

_log = logging.getLogger("config_watcher")


class _ConfigReloadHandler(FileSystemEventHandler):
    def __init__(self, callback: Callable[[str], None], watched: Set[str]) -> None:
        super().__init__()
        self._callback = callback
        self._watched = watched
        self._debounce: float = 0.0

    def on_modified(self, event: FileModifiedEvent) -> None:
        if event.is_directory:
            return
        path = os.path.normpath(event.src_path)
        if path not in self._watched:
            return
        now = time.time()
        if now - self._debounce < 1.0:
            return
        self._debounce = now
        _log.info("Config file changed: %s — reloading", path)
        try:
            self._callback(path)
        except Exception as exc:
            _log.error("Config reload callback failed for %s: %s", path, exc)


class ConfigWatcher:
    """Watches config YAML files for changes and triggers a reload callback.

    Usage:
        watcher = ConfigWatcher(controller.reload_config)
        watcher.start()
        ...
        watcher.stop()
    """

    def __init__(self, callback: Callable[[str], None]) -> None:
        self._callback = callback
        self._observer: Optional[Observer] = None

    def start(self, *paths: str) -> None:
        watched: Set[str] = set()
        for p in paths:
            norm = os.path.normpath(os.path.abspath(p))
            if os.path.isfile(norm):
                watched.add(norm)

        if not watched:
            _log.debug("ConfigWatcher: no files to watch.")
            return

        handler = _ConfigReloadHandler(self._callback, watched)
        dirs_to_watch = {os.path.dirname(p) for p in watched}

        self._observer = Observer()
        for d in dirs_to_watch:
            if os.path.isdir(d):
                self._observer.schedule(handler, d, recursive=False)

        self._observer.start()
        _log.info("ConfigWatcher: watching %d file(s)", len(watched))

    def stop(self) -> None:
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=3.0)
            except Exception as exc:
                _log.debug("ConfigWatcher stop: %s", exc)
            self._observer = None
            _log.info("ConfigWatcher: stopped")

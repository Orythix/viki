"""PluginLoader — dynamic discovery and loading of tool plugins."""

from __future__ import annotations

import importlib
import inspect
import logging
import os
import pkgutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .base import BaseTool

logger = logging.getLogger(__name__)


@dataclass
class PluginInfo:
    name: str
    module_path: str
    class_name: str
    tool_class: type[BaseTool] | None = None
    error: str | None = None


class PluginLoader:
    def __init__(self, plugin_dirs: list[str] | None = None, auto_discover: bool = True):
        self._plugin_dirs: list[str] = plugin_dirs or []
        self._plugins: dict[str, PluginInfo] = {}
        self._instances: dict[str, BaseTool] = {}
        if auto_discover:
            self.discover_all()

    def discover_all(self) -> list[PluginInfo]:
        discovered: list[PluginInfo] = []
        for dir_path in self._plugin_dirs:
            discovered.extend(self._discover_from_dir(dir_path))
        discovered.extend(self._discover_from_entry_points())
        for info in discovered:
            if info.error is None:
                self._plugins[info.name] = info
        return discovered

    def _discover_from_dir(self, dir_path: str) -> list[PluginInfo]:
        results: list[PluginInfo] = []
        path = Path(dir_path)
        if not path.is_dir():
            return results
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
        package_name = path.stem
        try:
            pkg = importlib.import_module(package_name)
        except Exception:
            return results
        for _, modname, ispkg in pkgutil.iter_modules(pkg.__path__ if hasattr(pkg, "__path__") else [str(path)]):
            if ispkg:
                continue
            full_modname = f"{package_name}.{modname}"
            results.extend(self._scan_module(full_modname, modname))
        return results

    def _discover_from_entry_points(self) -> list[PluginInfo]:
        results: list[PluginInfo] = []
        try:
            from importlib.metadata import entry_points
            eps = entry_points(group="viki.tools")
            for ep in eps:
                try:
                    cls = ep.load()
                    if isinstance(cls, type) and issubclass(cls, BaseTool) and cls is not BaseTool:
                        name = getattr(cls, "name", None) or ep.name
                        results.append(PluginInfo(
                            name=name,
                            module_path=ep.value,
                            class_name=cls.__name__,
                            tool_class=cls,
                        ))
                except Exception as exc:
                    logger.debug("PluginLoader: failed to load entry point %s: %s", ep.name, exc)
        except Exception:
            pass
        return results

    def _scan_module(self, full_modname: str, display_name: str) -> list[PluginInfo]:
        results: list[PluginInfo] = []
        try:
            mod = importlib.import_module(full_modname)
        except Exception as exc:
            logger.debug("PluginLoader: cannot import %s: %s", full_modname, exc)
            return results
        for name, obj in inspect.getmembers(mod, inspect.isclass):
            if obj is BaseTool:
                continue
            if issubclass(obj, BaseTool) and not getattr(obj, "__abstractmethods__", None):
                tool_name = getattr(obj, "name", None) or name
                results.append(PluginInfo(
                    name=tool_name,
                    module_path=full_modname,
                    class_name=name,
                    tool_class=obj,
                ))
        return results

    def get_tool_class(self, name: str) -> type[BaseTool] | None:
        info = self._plugins.get(name)
        if info is None:
            return None
        if info.tool_class is not None:
            return info.tool_class
        try:
            mod = importlib.import_module(info.module_path)
            cls = getattr(mod, info.class_name, None)
            if cls is not None and isinstance(cls, type) and issubclass(cls, BaseTool):
                info.tool_class = cls
                return cls
        except Exception as exc:
            info.error = str(exc)
        return None

    def instantiate(self, name: str, **kwargs) -> BaseTool | None:
        cls = self.get_tool_class(name)
        if cls is None:
            return None
        if name in self._instances:
            return self._instances[name]
        try:
            instance = cls(**kwargs)
            self._instances[name] = instance
            return instance
        except Exception as exc:
            logger.error("PluginLoader: failed to instantiate %s: %s", name, exc)
            return None

    def list_plugins(self, loaded_only: bool = False) -> list[PluginInfo]:
        if loaded_only:
            return [info for info in self._plugins.values() if info.tool_class is not None]
        return list(self._plugins.values())

    def add_plugin_dir(self, dir_path: str) -> list[PluginInfo]:
        if dir_path not in self._plugin_dirs:
            self._plugin_dirs.append(dir_path)
        results = self._discover_from_dir(dir_path)
        for info in results:
            if info.error is None:
                self._plugins[info.name] = info
        return results

    def reload(self, name: str) -> bool:
        info = self._plugins.get(name)
        if info is None:
            return False
        self._instances.pop(name, None)
        info.tool_class = None
        info.error = None
        return self.get_tool_class(name) is not None

"""Central tool registry with auto-discovery support and TTL result cache."""

from __future__ import annotations

import importlib.util
import inspect
import logging
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

# TTL for cached tool results (seconds)
_CACHE_TTL = 30
# Tool name prefixes that are safe to cache (idempotent, read-only)
_CACHEABLE_PREFIXES = ("filesystem.read", "filesystem.list", "filesystem.search")


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
        self._categories: dict[str, list[str]] = defaultdict(list)
        self._cache: dict[str, tuple[float, ToolResult]] = {}
        self._lock = threading.Lock()

    def register(self, tool: BaseTool):
        with self._lock:
            self._tools[tool.name] = tool
            for cap in tool.capabilities:
                self._categories[cap].append(tool.name)

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def get_tool_definitions(self) -> list[dict]:
        return [t.get_tool_definition() for t in self._tools.values()]

    async def execute(self, name: str, params: dict, **kwargs) -> ToolResult:
        tool = self._tools.get(name)
        if not tool:
            from .base import ToolResult

            return ToolResult(success=False, error=f"Unknown tool: {name}")

        # Check TTL cache for idempotent tools
        cache_key = f"{name}:{params!r}"
        if name.startswith(_CACHEABLE_PREFIXES):
            cached = self._cache.get(cache_key)
            if cached is not None:
                ts, result = cached
                if time.monotonic() - ts < _CACHE_TTL:
                    return result

        try:
            result = await tool.execute(params, **kwargs)
        except Exception as e:
            from .base import ToolResult

            result = ToolResult(success=False, error=str(e), error_type="execution_failed")

        # Cache successful read-only results
        if name.startswith(_CACHEABLE_PREFIXES) and getattr(result, "success", False):
            self._cache[cache_key] = (time.monotonic(), result)

        return result

    def invalidate_cache(self, name: str | None = None):
        """Clear cached results for a specific tool, or all if name is None."""
        if name is None:
            self._cache.clear()
        else:
            prefix = f"{name}:"
            self._cache = {k: v for k, v in self._cache.items() if not k.startswith(prefix)}

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def discover(self, *paths: str | Path) -> int:
        """Scan directories/files for tool modules and auto-register them.

        Supports two naming conventions:
          - ``*_tool.py`` files (e.g. ``docker_tool.py``)
          - ``tool.py`` inside subdirectories (e.g. ``database/tool.py``)

        Returns the number of tools registered.
        """
        from .base import BaseTool

        count = 0
        seen: set[Any] = set()

        for raw in paths:
            path = Path(raw)
            if not path.exists():
                logger.debug("Tool discovery: path '%s' does not exist, skipping", path)
                continue

            if path.is_file():
                count += self._discover_file(path, BaseTool, seen)
            elif path.is_dir():
                # Single glob pass to reduce filesystem I/O
                for file in sorted(path.rglob("*.py")):
                    fname = file.name
                    if not fname.endswith("_tool.py") and fname != "tool.py":
                        continue
                    if file in seen:
                        continue
                    # Skip tool.py inside __pycache__ or vendor dirs
                    if "_pycache_" in file.parts or "site-packages" in file.parts:
                        continue
                    # Skip tool.py when parent == grandparent (flat nesting)
                    if fname == "tool.py" and file.parent.name == file.parent.parent.name:
                        continue
                    count += self._discover_file(file, BaseTool, seen)

        return count

    def discover_plugins(self, *plugin_dirs: str | Path) -> int:
        """Discover tool plugins from plugin directories (installable packages)."""
        return self.discover(*plugin_dirs)

    def _discover_file(self, file: Path, base_cls: type, seen: set[Path]) -> int:
        """Load a single file and register any BaseTool subclasses found."""
        if file in seen:
            return 0
        seen.add(file)

        # Find the `src` root to compute proper package context
        src_root = self._find_src_root(file)
        package = self._compute_package(file, src_root)

        try:
            spec = importlib.util.spec_from_file_location(
                file.stem,
                file,
                submodule_search_locations=None,
            )
            if spec is None or spec.loader is None:
                logger.warning("Tool discovery: cannot load '%s'", file)
                return 0

            mod = importlib.util.module_from_spec(spec)
            mod.__package__ = package

            # Store reference to prevent GC
            import sys

            if package:
                parts = package.split(".")
                for i in range(len(parts)):
                    parent = ".".join(parts[: i + 1])
                    if parent not in sys.modules:
                        sys.modules[parent] = __import__(parent.split(".")[0])

            spec.loader.exec_module(mod)

            count = 0
            for attr_name in dir(mod):
                if attr_name.startswith("_"):
                    continue
                cls = getattr(mod, attr_name)
                if (
                    isinstance(cls, type)
                    and issubclass(cls, base_cls)
                    and cls is not base_cls
                    and not inspect.isabstract(cls)
                ):
                    try:
                        instance = cls()
                        if instance.name not in self._tools:
                            self.register(instance)
                            count += 1
                            logger.debug(
                                "Tool discovery: registered '%s' from %s",
                                instance.name,
                                file,
                            )
                    except Exception as e:
                        logger.warning(
                            "Tool discovery: failed to instantiate %s from %s: %s",
                            cls.__name__,
                            file,
                            e,
                        )
            return count
        except Exception as e:
            logger.warning("Tool discovery: error loading '%s': %s", file, e)
            return 0

    @staticmethod
    def _find_src_root(file: Path) -> Path:
        """Walk up from `file` to find the `src` directory."""
        for parent in [file] + list(file.parents):
            if parent.name == "src" and (parent / "viki").is_dir():
                return parent
        return file.parent

    @staticmethod
    def _compute_package(file: Path, src_root: Path) -> str:
        """Compute the Python package path for a file relative to src_root.

        E.g. ``src/viki/v2/tools/system/tool.py`` → ``viki.v2.tools.system``
        """
        try:
            rel = file.parent.relative_to(src_root)
            parts = list(rel.parts)
            if file.stem == "__init__":
                return ".".join(parts)
            return ".".join(parts)
        except ValueError:
            return ""

    def save(self, path: str | Path):
        """Persist the current tool registry to a JSON file."""
        import json

        data = {
            name: {
                "module": getattr(tool, "__module__", ""),
                "description": getattr(tool, "description", ""),
            }
            for name, tool in self._tools.items()
        }
        Path(path).write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path: str | Path) -> ToolRegistry:
        """Load a previously saved registry from a JSON file."""
        import json

        registry = cls()
        data = json.loads(Path(path).read_text())
        for name in data:
            logger.debug("Registry load: '%s' was registered", name)
        return registry

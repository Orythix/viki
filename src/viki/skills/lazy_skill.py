"""
LazySkillProxy — defer heavy skill imports until first use.

Many built-in skills import optional, expensive packages at import time
(`torch`, `pillow`, `playwright`, `pandas`, `pdfplumber`, `whisper`,
`onnxruntime`, `transformers`, …). On low-end PCs that can add 5–15 s to
startup and 200–800 MB of RAM that may never be needed.

This proxy registers in the SkillRegistry as a normal `BaseSkill` but
only constructs the underlying skill on the first `execute(...)` call.
The proxy advertises a stable `name`, `description`, and `schema` from a
metadata dict so the planner / context builder can list the skill
without paying the import cost.

Usage:

    proxy = LazySkillProxy(
        name="vision",
        description="Capture a screenshot and describe it.",
        module_path="viki.skills.builtins.vision_skill",
        class_name="VisionSkill",
        ctor_args=lambda controller: (),
        controller=controller,
    )
    skill_registry.register_skill(proxy)

The first `await proxy.execute(...)` triggers the import + instantiation,
caches the underlying skill on the proxy, and proxies all further calls
straight through.
"""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Callable
from typing import Any

from viki.config.logger import viki_logger
from viki.skills.base import BaseSkill


class LazySkillProxy(BaseSkill):
    """Wrap a heavy skill so it loads on first execute()."""

    def __init__(
        self,
        *,
        name: str,
        description: str,
        module_path: str,
        class_name: str,
        ctor_args: Callable[[Any], tuple] | None = None,
        controller: Any = None,
        schema: dict[str, Any] | None = None,
        safety_tier: str = "safe",
        triggers: list[str] | None = None,
        version: str = "1.0.0",
    ):
        self._name = name
        self._description = description
        self._module_path = module_path
        self._class_name = class_name
        self._ctor_args = ctor_args
        self._controller = controller
        self._schema = schema or {}
        self._safety_tier = safety_tier
        self._triggers = list(triggers or [])
        self._version = version
        self._real: BaseSkill | None = None
        self._lock = asyncio.Lock()
        self._load_failed: str | None = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def version(self) -> str:
        return self._version

    @property
    def schema(self) -> dict[str, Any]:
        if self._real is not None:
            try:
                return self._real.schema or self._schema
            except Exception:
                return self._schema
        return self._schema

    @property
    def safety_tier(self) -> str:
        if self._real is not None:
            try:
                return self._real.safety_tier
            except Exception:
                return self._safety_tier
        return self._safety_tier

    @property
    def triggers(self) -> list[str]:
        if self._real is not None:
            try:
                return self._real.triggers or self._triggers
            except Exception:
                return self._triggers
        return self._triggers

    def is_loaded(self) -> bool:
        return self._real is not None

    async def _load(self) -> BaseSkill | None:
        if self._real is not None:
            return self._real
        if self._load_failed:
            return None
        async with self._lock:
            if self._real is not None:
                return self._real
            try:
                module = importlib.import_module(self._module_path)
                cls = getattr(module, self._class_name)
                args: tuple = ()
                if self._ctor_args is not None:
                    args = self._ctor_args(self._controller) or ()
                self._real = cls(*args)
                viki_logger.debug("LazySkillProxy: loaded '%s' on first use.", self._name)
                return self._real
            except Exception as e:
                self._load_failed = str(e)
                viki_logger.warning("LazySkillProxy: failed to load '%s': %s", self._name, e)
                return None

    async def execute(self, params: dict[str, Any]) -> str:
        skill = await self._load()
        if skill is None:
            return f"Error: skill '{self._name}' is unavailable ({self._load_failed or 'unknown'})."

        # Circuit breaker check
        registry = getattr(self._controller, "skill_registry", None)
        if registry is not None and hasattr(registry, "is_skill_available"):
            if not registry.is_skill_available(self._name):
                return f"Skill '{self._name}' is temporarily unavailable (circuit open). Try again later."

        import time

        start = time.time()
        try:
            result = await skill.execute(params or {})
            elapsed = time.time() - start
            if registry is not None and hasattr(registry, "record_execution"):
                registry.record_execution(self._name, True, elapsed)
            return result
        except Exception:
            elapsed = time.time() - start
            if registry is not None and hasattr(registry, "record_execution"):
                registry.record_execution(self._name, False, elapsed)
            raise

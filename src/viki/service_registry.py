"""
Lightweight Dependency Injection Container for VIKI.

Replaces the `dependency_injector` package with a zero-dependency
pure-Python implementation that exposes an identical public API so
callers in main.py do not need to change.

  container = Container()
  container.config.from_yaml(path)
  svc = container.safety_service()
  ...
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any, TypeVar

import yaml

T = TypeVar("T")

_log = logging.getLogger("container")


# ---------------------------------------------------------------------------
# Config proxy
# ---------------------------------------------------------------------------
class _ConfigProxy:
    """Holds flat/nested config and allows attribute-style access."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def from_yaml(self, path: str) -> None:
        if not os.path.exists(path):
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if isinstance(data, dict):
                self._data.update(data)
        except Exception as exc:
            _log.warning("Config load from %s failed: %s", path, exc)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def __getattr__(self, key: str) -> Any:
        # Allow container.config.safety etc. – returns a nested proxy or value.
        val = self._data.get(key)
        if isinstance(val, dict):
            proxy = _ConfigProxy()
            proxy._data = val
            return proxy
        return val


# ---------------------------------------------------------------------------
# Singleton / Factory descriptors
# ---------------------------------------------------------------------------
class _Singleton:
    """Lazily constructs and caches a single instance."""

    def __init__(self, factory: Callable[[], Any]) -> None:
        self._factory = factory
        self._instance: Any | None = None

    def __call__(self) -> Any:
        if self._instance is None:
            self._instance = self._factory()
        return self._instance


class _Factory:
    """Creates a new instance on every call."""

    def __init__(self, factory: Callable[[], Any]) -> None:
        self._factory = factory

    def __call__(self) -> Any:
        return self._factory()


# ---------------------------------------------------------------------------
# Container
# ---------------------------------------------------------------------------
class Container:
    """
    Pure-Python DI container with the same public interface as the previous
    `dependency_injector`-based implementation.
    """

    def __init__(self) -> None:
        self.config = _ConfigProxy()
        self._singletons: dict[str, _Singleton] = {}
        self._factories: dict[str, _Factory] = {}
        self._build()

    # ------------------------------------------------------------------
    # Internal wiring
    # ------------------------------------------------------------------
    def _build(self) -> None:
        """Register all providers lazily so imports only happen on first use."""
        self._init_errors: dict[str, str] = {}

        def _make_learning_repository():
            try:
                from viki.infrastructure.database.sqlalchemy_learning_repository import (
                    SqlAlchemyLearningRepository,
                )

                return SqlAlchemyLearningRepository(db_path="data/viki_knowledge.db")
            except Exception as exc:
                msg = f"learning_repository init failed: {exc}"
                _log.warning(msg)
                self._init_errors["learning_repository"] = str(exc)
                return None

        def _make_agent_pool():
            try:
                from viki.infrastructure.swarm.local_agent_pool import LocalAgentPool

                return LocalAgentPool()
            except Exception as exc:
                msg = f"agent_pool init failed: {exc}"
                _log.warning(msg)
                self._init_errors["agent_pool"] = str(exc)
                return None

        def _make_safety_service():
            try:
                from viki.application.services.safety_service import SafetyService

                return SafetyService(config=self.config.get("safety", {}))
            except Exception as exc:
                msg = f"safety_service init failed: {exc}"
                _log.warning(msg)
                self._init_errors["safety_service"] = str(exc)
                return None

        def _make_swarm_orchestrator():
            try:
                from viki.application.services.swarm_orchestrator import SwarmOrchestrator

                pool = self.agent_pool()
                return SwarmOrchestrator(agent_pool=pool)
            except Exception as exc:
                msg = f"swarm_orchestrator init failed: {exc}"
                _log.warning(msg)
                self._init_errors["swarm_orchestrator"] = str(exc)
                return None

        def _make_forge_orchestrator():
            try:
                from viki.application.services.forge_orchestrator import ForgeOrchestrator

                return ForgeOrchestrator(controller=None)
            except Exception as exc:
                msg = f"forge_orchestrator init failed: {exc}"
                _log.warning(msg)
                self._init_errors["forge_orchestrator"] = str(exc)
                return None

        def _make_self_healing():
            try:
                from viki.application.services.fault_tolerance_service import SelfHealingService

                return SelfHealingService(controller=None)
            except Exception as exc:
                msg = f"self_healing_service init failed: {exc}"
                _log.warning(msg)
                self._init_errors["self_healing_service"] = str(exc)
                return None

        def _make_recall_use_case():
            try:
                from viki.application.use_cases.recall_memory import MemoryRecallUseCase

                return MemoryRecallUseCase(
                    learning_repo=self.learning_repository(),
                    safety_service=self.safety_service(),
                )
            except Exception as exc:
                msg = f"recall_memory_use_case init failed: {exc}"
                _log.warning(msg)
                self._init_errors["recall_memory_use_case"] = str(exc)
                return None

        # Singletons
        self._singletons["learning_repository"] = _Singleton(_make_learning_repository)
        self._singletons["agent_pool"] = _Singleton(_make_agent_pool)
        self._singletons["safety_service"] = _Singleton(_make_safety_service)
        self._singletons["swarm_orchestrator"] = _Singleton(_make_swarm_orchestrator)
        self._singletons["forge_orchestrator"] = _Singleton(_make_forge_orchestrator)
        self._singletons["self_healing_service"] = _Singleton(_make_self_healing)

        # Factories
        self._factories["recall_memory_use_case"] = _Factory(_make_recall_use_case)

    # ------------------------------------------------------------------
    # Public accessors (mirror dependency_injector attribute style)
    # ------------------------------------------------------------------
    def __getattr__(self, name: str) -> Any:
        singletons = object.__getattribute__(self, "_singletons")
        factories = object.__getattribute__(self, "_factories")
        if name in singletons:
            return singletons[name]
        if name in factories:
            return factories[name]
        raise AttributeError(f"Container has no provider '{name}'")

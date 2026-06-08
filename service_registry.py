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

import os
from typing import Any, Callable, Dict, Optional, Type, TypeVar

import yaml

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Config proxy
# ---------------------------------------------------------------------------
class _ConfigProxy:
    """Holds flat/nested config and allows attribute-style access."""

    def __init__(self) -> None:
        self._data: Dict[str, Any] = {}

    def from_yaml(self, path: str) -> None:
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if isinstance(data, dict):
                self._data.update(data)
        except Exception:
            pass  # Non-fatal – controller will load settings independently.

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
        self._instance: Optional[Any] = None

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
        self._singletons: Dict[str, _Singleton] = {}
        self._factories: Dict[str, _Factory] = {}
        self._build()

    # ------------------------------------------------------------------
    # Internal wiring
    # ------------------------------------------------------------------
    def _build(self) -> None:
        """Register all providers lazily so imports only happen on first use."""

        def _make_learning_repository():
            try:
                from infrastructure.database.sqlalchemy_learning_repository import (
                    SqlAlchemyLearningRepository,
                )
                return SqlAlchemyLearningRepository(db_url="sqlite:///data/viki_knowledge.db?timeout=30.0")
            except Exception:
                return None

        def _make_agent_pool():
            try:
                from infrastructure.swarm.local_agent_pool import LocalAgentPool
                return LocalAgentPool()
            except Exception:
                return None

        def _make_safety_service():
            try:
                from application.services.safety_service import SafetyService
                return SafetyService(config=self.config.get("safety", {}))
            except Exception:
                return None

        def _make_swarm_orchestrator():
            try:
                from application.services.swarm_orchestrator import SwarmOrchestrator
                pool = self.agent_pool()
                return SwarmOrchestrator(agent_pool=pool)
            except Exception:
                return None

        def _make_forge_orchestrator():
            try:
                from application.services.forge_orchestrator import ForgeOrchestrator
                # controller is injected later by main.py
                return ForgeOrchestrator(controller=None)
            except Exception:
                return None

        def _make_self_healing():
            try:
                from application.services.fault_tolerance_service import SelfHealingService
                # controller is injected later by main.py
                return SelfHealingService(controller=None)
            except Exception:
                return None

        def _make_recall_use_case():
            try:
                from application.use_cases.recall_memory import MemoryRecallUseCase
                return MemoryRecallUseCase(
                    learning_repo=self.learning_repository(),
                    safety_service=self.safety_service(),
                )
            except Exception:
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

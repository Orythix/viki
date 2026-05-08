"""
Shared pytest fixtures.

Live tests are skipped unless QA_LIVE_API=1 so CI stays fast and deterministic.
"""
from __future__ import annotations

import os

import pytest

from qa_lab.client import SecurityLabClient
from qa_lab.config import Settings


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "live: requires running API + QA_LIVE_API=1")


def _live_enabled() -> bool:
    return os.environ.get("QA_LIVE_API", "").lower() in ("1", "true", "yes")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Function]) -> None:
    if _live_enabled():
        return
    skip = pytest.mark.skip(reason="Live API tests: set QA_LIVE_API=1 and run security-lab (see qa-automation/README.md)")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def settings() -> Settings:
    return Settings.from_env()


@pytest.fixture
def api_client(settings: Settings) -> SecurityLabClient:
    return SecurityLabClient(settings)

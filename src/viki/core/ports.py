"""
Narrow capability ports for dependency injection (see ARCHITECTURE_REFACTOR.md).
Controllers implement these protocols structurally; callers depend on the interface only.
"""

from __future__ import annotations

from typing import Any, Protocol


class RequestProcessorPort(Protocol):
    """Brain entrypoint used by Nexus, MissionControl, and similar ingress."""

    async def process_request(
        self,
        user_input: str,
        on_event: Any = None,
        on_think: Any = None,
        attachment_paths: list[str] | None = None,
        session_id: str | None = None,
    ) -> str:
        ...

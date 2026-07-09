"""VIKI API Module (Messaging Gateways & Nexus)."""

from __future__ import annotations

from typing import Any

from aiohttp.web_app import AppKey

# Shared app key used to store the VIKIController reference on the
# aiohttp web.Application instance (avoids aiohttp AppKey warnings).
CONTROLLER_KEY: AppKey[Any] = AppKey("viki_controller", Any)
__all__ = ["CONTROLLER_KEY"]

"""Three-tier permission system."""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class PermissionTier(enum.Enum):
    SAFE = "safe"
    ELEVATED = "elevated"
    ADMIN = "admin"


@dataclass
class PermissionCheck:
    allowed: bool
    timeout: int = 30
    notify: bool = False
    confirmed: bool = False
    reason: str = ""


class PermissionManager:
    def __init__(self, tool_registry=None):
        self.tool_registry = tool_registry
        self._admin_session = False

    def set_admin_session(self, active: bool):
        self._admin_session = active

    async def check(self, tool_name: str, params: dict, session_id: str = "") -> PermissionCheck:
        tool = None
        if self.tool_registry:
            tool = self.tool_registry._tools.get(tool_name)
        if tool is None:
            return PermissionCheck(False, reason=f"Unknown tool: {tool_name}")

        tier = tool.permission_tier

        if tier == PermissionTier.SAFE:
            return PermissionCheck(True, timeout=30)

        if tier == PermissionTier.ELEVATED:
            logger.info("Elevated tool used: %s params=%s", tool_name, params)
            return PermissionCheck(True, timeout=60, notify=True)

        if tier == PermissionTier.ADMIN:
            if self._admin_session:
                return PermissionCheck(True, timeout=120, confirmed=True)
            return PermissionCheck(False, reason="Action requires admin confirmation")

        return PermissionCheck(False, reason="Unknown permission tier")

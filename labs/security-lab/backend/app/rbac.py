"""Load RBAC policy JSON and check permissions."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Set

logger = logging.getLogger(__name__)


class RBACPolicy:
    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._data = self._load()

    def _load(self) -> Dict[str, Any]:
        if not self._path.is_file():
            logger.error("rbac_policy_missing", extra={"extra_fields": {"path": str(self._path)}})
            return {"roles": {}, "default_role": "observer"}
        with open(self._path, encoding="utf-8") as f:
            return json.load(f)

    def permissions_for(self, role: str) -> Set[str]:
        roles = self._data.get("roles") or {}
        r = roles.get(role) or roles.get(self._data.get("default_role", "observer")) or {}
        perms = r.get("permissions") or []
        return set(str(p) for p in perms)

    def allowed(self, role: str, permission: str) -> bool:
        return permission in self.permissions_for(role)

    def default_role(self) -> str:
        return str(self._data.get("default_role", "observer"))

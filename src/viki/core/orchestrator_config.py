"""Settings, config-file resolution, and small filesystem helpers.

Extracted from the VIKIController god-module; mixed into
viki.core.orchestrator.VIKIController.
"""

import os
from typing import Any

from viki.core.orchestrator_helpers import (
    _build_env_nested_overrides,
    _build_env_overrides,
    load_yaml,
    persona_from_soul_path,
    read_json,
    read_text_truncated,
    write_json,
)


class ControllerConfigMixin:
    def _write_json(self, path: str, payload: Any, indent: int | None = None) -> None:
        write_json(path, payload, indent)

    def _read_json(self, path: str) -> Any:
        return read_json(path)

    def _read_text_truncated(self, path: str, max_len: int) -> str:
        return read_text_truncated(path, max_len)

    def _apply_system_overrides(
        self, system: dict[str, Any], workspace_override: str | None
    ) -> None:
        """Apply env/YAML overrides to the `system` settings dict."""
        system.update(_build_env_overrides())
        for section, values in _build_env_nested_overrides().items():
            existing = self.settings.setdefault(section, {})
            if not isinstance(existing, dict):
                existing = {}
                self.settings[section] = existing
            existing.update(values)
        if workspace_override:
            system["workspace_dir"] = os.path.abspath(workspace_override)

    def _resolve_models_config(self) -> None:
        models_conf_rel = self.settings.get("models_config", "./config/models.yaml")
        if models_conf_rel.startswith("./"):
            models_conf_rel = models_conf_rel[2:]
        settings_dir = os.path.dirname(os.path.abspath(self.settings_path))
        self.models_config_path = os.path.join(settings_dir, models_conf_rel)
        self.models_config = self._load_yaml(self.models_config_path)

    def _resolve_security_layer_path(self) -> None:
        if "security_layer_path" not in self.settings:
            return
        sec_path = self.settings["security_layer_path"]
        if sec_path.startswith("./"):
            sec_path = sec_path[2:]
        settings_dir = os.path.dirname(os.path.abspath(self.settings_path))
        candidate = os.path.join(settings_dir, sec_path)
        if not os.path.exists(candidate):
            candidate_viki = os.path.join(settings_dir, "..", "viki", sec_path)
            if os.path.exists(candidate_viki):
                candidate = candidate_viki
        self.settings["security_layer_path"] = candidate

    def _init_db(self):
        """Ensure core data directories exist."""
        system = self.settings.get("system", {})
        data_dir = system.get("data_dir", self.DEFAULT_DATA_DIR)
        os.makedirs(data_dir, exist_ok=True)
        workspace_dir = system.get("workspace_dir", self.DEFAULT_WORKSPACE_DIR)
        os.makedirs(workspace_dir, exist_ok=True)

    def _load_yaml(self, path: str) -> dict[str, Any]:
        return load_yaml(path)

    def _persona_from_soul_path(self, soul_path: str) -> str:
        return persona_from_soul_path(soul_path)

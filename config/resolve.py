"""
Resolve soul/persona config path from settings and VIKI_PERSONA env.
"""
import os
import yaml


def get_soul_path(settings_path: str) -> str:
    """
    Resolve the path to the soul (or persona) YAML file.
    - If VIKI_PERSONA is set, use config/personas/{persona}.yaml.
    - Else if system.persona is set in settings, use config/personas/{persona}.yaml.
    - Else use config/soul.yaml if it exists; otherwise config/personas/sovereign.yaml.
    """
    config_dir = os.path.dirname(os.path.abspath(settings_path))
    persona = os.environ.get("VIKI_PERSONA", "").strip()
    if not persona:
        try:
            with open(settings_path, "r") as f:
                settings = yaml.safe_load(f)
            persona = (settings.get("system") or {}).get("persona", "").strip()
        except Exception as e:
            import logging
            logging.getLogger("viki").debug("Resolve soul path: %s", e)
    if persona:
        path = os.path.join(config_dir, "personas", f"{persona}.yaml")
        if os.path.exists(path):
            return path
    soul_path = os.path.join(config_dir, "soul.yaml")
    if os.path.exists(soul_path):
        return soul_path
    return os.path.join(config_dir, "personas", "sovereign.yaml")

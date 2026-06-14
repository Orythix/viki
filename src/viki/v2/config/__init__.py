"""V2 configuration — Pydantic-based settings with nested sections, env vars, .env, hot-reload, secrets, CLI overrides, JSON Schema, and include support."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ── Section models ─────────────────────────────────────────────────────────────


class LLMConfig(BaseModel):
    model: str = "gemma4:12b"
    host: str = "http://127.0.0.1:11434"
    temperature: float = 0.7
    max_steps: int = 10

    @field_validator("temperature")
    @classmethod
    def _clamp_temperature(cls, v: float) -> float:
        return max(0.0, min(2.0, v))

    @field_validator("max_steps")
    @classmethod
    def _positive_steps(cls, v: int) -> int:
        if v < 1:
            raise ValueError("max_steps must be >= 1")
        return v

    @field_validator("host")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")


class MemoryConfig(BaseModel):
    max_turns: int = 50

    @field_validator("max_turns")
    @classmethod
    def _positive_turns(cls, v: int) -> int:
        return max(1, v)


class ToolsConfig(BaseModel):
    mcp_config_path: str = "config/mcp_servers.yaml"
    plugin_dirs: list[str] = Field(default_factory=list)
    tool_permissions: dict[str, str] = Field(default_factory=dict)


class UIConfig(BaseModel):
    theme: str = "dark"
    log_level: str = "INFO"


class DataConfig(BaseModel):
    dir: str = "./data"


# ── Flat ↔ nested mapping ─────────────────────────────────────────────────────

_FLAT_TO_SUB: dict[str, tuple[str, str]] = {
    "model": ("llm", "model"),
    "ollama_host": ("llm", "host"),
    "temperature": ("llm", "temperature"),
    "max_steps": ("llm", "max_steps"),
    "memory_max_turns": ("memory", "max_turns"),
    "mcp_config_path": ("tools", "mcp_config_path"),
    "plugin_dirs": ("tools", "plugin_dirs"),
    "tool_permissions": ("tools", "tool_permissions"),
    "theme": ("ui", "theme"),
    "log_level": ("ui", "log_level"),
    "data_dir": ("data", "dir"),
}

_SUB_TO_FLAT = {(v[0], v[1]): k for k, v in _FLAT_TO_SUB.items()}


def _flat_to_nested(data: dict) -> dict:
    """Convert flat keys (``model``) to nested section dict (``{"llm": {"model": ...}}``)."""
    result: dict[str, Any] = {}
    for k, v in data.items():
        if k in _FLAT_TO_SUB:
            section, field = _FLAT_TO_SUB[k]
            if section not in result:
                result[section] = {}
            result[section][field] = v
        elif k not in ("llm", "memory", "tools", "ui", "data"):
            result[k] = v
        else:
            # Already a section — merge into existing
            if k not in result:
                result[k] = v
            elif isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = _deep_merge(result[k], v)
            else:
                result[k] = v
    return result


def _nested_to_flat(data: dict) -> dict:
    """Convert nested section dict back to flat keys."""
    result: dict[str, Any] = {}
    for section, fields in data.items():
        if isinstance(fields, dict):
            for field_name, val in fields.items():
                flat = _SUB_TO_FLAT.get((section, field_name))
                if flat is not None:
                    result[flat] = val
        elif section not in ("llm", "memory", "tools", "ui", "data"):
            result[section] = fields
    return result


# ── Top-level config ──────────────────────────────────────────────────────────


class V2Config(BaseModel):
    """Central VIKI v2 configuration with nested sections and backward-compat flat properties.

    Accepts both flat kwargs (``V2Config(model="foo", temperature=0.3)``)
    and nested dict (``V2Config(llm={"model": "foo", "temperature": 0.3})``).
    """

    model_config = ConfigDict(frozen=True)

    llm: LLMConfig = Field(default_factory=LLMConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    data: DataConfig = Field(default_factory=DataConfig)

    # ── Backward-compat flat properties ──────────────────────────────

    @property
    def model(self) -> str:
        return self.llm.model

    @property
    def ollama_host(self) -> str:
        return self.llm.host

    @property
    def temperature(self) -> float:
        return self.llm.temperature

    @property
    def max_steps(self) -> int:
        return self.llm.max_steps

    @property
    def data_dir(self) -> str:
        return self.data.dir

    @property
    def theme(self) -> str:
        return self.ui.theme

    @property
    def log_level(self) -> str:
        return self.ui.log_level

    @property
    def mcp_config_path(self) -> str:
        return self.tools.mcp_config_path

    @property
    def plugin_dirs(self) -> list[str]:
        return self.tools.plugin_dirs

    @property
    def tool_permissions(self) -> dict[str, str]:
        return self.tools.tool_permissions

    @property
    def memory_max_turns(self) -> int:
        return self.memory.max_turns

    # ── Dual-format constructor ──────────────────────────────────────

    @model_validator(mode="before")
    @classmethod
    def _accept_flat_input(cls, data: Any) -> Any:
        """Accept both flat kwargs and nested dict."""
        if not isinstance(data, dict):
            return data
        if any(k in _FLAT_TO_SUB for k in data):
            return _flat_to_nested(data)
        return data

    # ── JSON Schema export ───────────────────────────────────────────

    @classmethod
    def generate_schema_file(cls, target: Path | None = None) -> str:
        """Write JSON Schema to a file for IDE autocomplete. Returns the path."""
        path = target or Path.home() / ".viki" / "viki.schema.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        schema = cls.model_json_schema()
        path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
        return str(path)


# ── File loading helpers ──────────────────────────────────────────────────────


def _find_config_file() -> Path | None:
    """Search for viki config in standard locations."""
    candidates = [
        Path.cwd() / "viki.yaml",
        Path.cwd() / "viki.json",
        Path.cwd() / "viki.yml",
        Path.cwd() / "config" / "viki.yaml",
        Path.cwd() / "config" / "viki.json",
        Path.home() / ".viki" / "config.yaml",
        Path.home() / ".viki" / "config.json",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def _load_config_file(path: Path) -> dict[str, Any]:
    """Load and parse a config file (JSON or YAML)."""
    ext = path.suffix.lower()
    if ext in (".yaml", ".yml"):
        try:
            import yaml

            with open(path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except ImportError:
            raise RuntimeError(
                "PyYAML is required to load .yaml config files. Install it with: pip install pyyaml"
            ) from None
    elif ext == ".json":
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep-merge override into base dict."""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _resolve_includes(raw: dict, base_dir: Path) -> dict:
    """Process ``include`` / ``includes`` directives in config dict."""
    includes = raw.pop("include", None) or raw.pop("includes", None)
    if not includes:
        return raw
    if isinstance(includes, str):
        includes = [includes]

    result: dict = {}
    for inc_path in includes:
        inc_file = Path(inc_path) if Path(inc_path).is_absolute() else base_dir / inc_path
        if inc_file.is_file():
            inc_data = _load_config_file(inc_file)
            result = _deep_merge(result, _resolve_includes(inc_data, inc_file.parent))

    result = _deep_merge(result, raw)
    return result


# ── Environment & .env ────────────────────────────────────────────────────────


def _load_dotenv(base_dir: Path | None = None) -> dict[str, str]:
    """Parse ``.env`` files from cwd and ``~/.viki/``."""
    result: dict[str, str] = {}
    candidates: list[Path] = [Path.cwd() / ".env"]
    if base_dir is not None and base_dir != Path.cwd():
        candidates.append(base_dir / ".env")
    candidates.append(Path.home() / ".viki" / ".env")

    seen = set()
    for path in candidates:
        if not path.is_file() or path in seen:
            continue
        seen.add(path)
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                result[k.strip()] = v.strip().strip("\"'")
    return result


_ENV_MAP: dict[str, tuple[str, str]] = {
    "VIKI_MODEL": ("llm", "model"),
    "OLLAMA_HOST": ("llm", "host"),
    "VIKI_DATA_DIR": ("data", "dir"),
    "VIKI_LOG_LEVEL": ("ui", "log_level"),
    "VIKI_MCP_CONFIG": ("tools", "mcp_config_path"),
    "VIKI_TEMPERATURE": ("llm", "temperature"),
    "VIKI_MAX_STEPS": ("llm", "max_steps"),
    "VIKI_THEME": ("ui", "theme"),
    "VIKI_MEMORY_MAX_TURNS": ("memory", "max_turns"),
}


def _load_env() -> dict[str, Any]:
    """Load settings from environment variables, including ``_FILE`` secrets."""
    result: dict[str, Any] = {}

    for env_var, (section, field) in _ENV_MAP.items():
        val = os.environ.get(env_var)
        if val is not None:
            result.setdefault(section, {})[field] = val

        # _FILE suffix: read value from a file path
        file_var = f"{env_var}_FILE"
        file_path = os.environ.get(file_var)
        if file_path:
            try:
                with open(file_path, encoding="utf-8") as f:
                    result.setdefault(section, {})[field] = f.read().strip()
            except OSError:
                pass

    return result


# ── CLI overrides ─────────────────────────────────────────────────────────────


def parse_cli_overrides(args: list[str] | None = None) -> tuple[dict[str, Any], argparse.Namespace]:
    """Parse CLI flags into flat config overrides.

    Returns ``(overrides_dict, parsed_namespace)``.
    """
    parser = argparse.ArgumentParser(description="VIKI v2", add_help=False)
    parser.add_argument("--model", help="LLM model name")
    parser.add_argument("--ollama-host", help="Ollama server URL")
    parser.add_argument("--temperature", type=float, help="LLM temperature")
    parser.add_argument("--max-steps", type=int, help="Max ReAct steps")
    parser.add_argument("--data-dir", help="Data directory")
    parser.add_argument("--theme", choices=["dark", "light"], help="UI theme")
    parser.add_argument("--log-level", help="Logging level")
    parser.add_argument("--mcp-config", help="MCP servers config path")
    parser.add_argument("--config", help="Config file path")
    parser.add_argument(
        "--generate-schema",
        action="store_true",
        help="Write JSON Schema to ~/.viki/viki.schema.json and exit",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch config file for changes and hot-reload",
    )
    parsed, _ = parser.parse_known_args(args)

    overrides: dict[str, Any] = {}
    mapping: dict[str, str] = {
        "model": "model",
        "ollama_host": "ollama_host",
        "temperature": "temperature",
        "max_steps": "max_steps",
        "data_dir": "data_dir",
        "theme": "theme",
        "log_level": "log_level",
        "mcp_config": "mcp_config_path",
    }
    for cli_flag, config_key in mapping.items():
        val = getattr(parsed, cli_flag, None)
        if val is not None:
            overrides[config_key] = val

    return overrides, parsed


# ── Hot-reload ────────────────────────────────────────────────────────────────


async def watch_config(
    path: Path | None = None,
    interval: float = 1.0,
) -> AsyncIterator[V2Config]:
    """Async generator that yields config on file changes.

    Polls the config file's mtime every ``interval`` seconds.
    Yields the initial config, then yields again whenever the file changes.
    """
    watch_path = path or _find_config_file()
    if watch_path is None:
        return
    last_mtime = watch_path.stat().st_mtime
    yield get_config(watch_path)
    while True:
        try:
            mtime = watch_path.stat().st_mtime
            if mtime != last_mtime:
                last_mtime = mtime
                yield load_config(watch_path)
        except OSError:
            pass
        await asyncio.sleep(interval)


# ── Public API ────────────────────────────────────────────────────────────────


def load_config(
    path: str | Path | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> V2Config:
    """Load V2 configuration from config file + ``.env`` + env vars + CLI flags.

    Resolution order (later wins):
      1. Pydantic model defaults
      2. Included config files (``include:`` YAML directive)
      3. Config file (``viki.yaml`` / ``viki.json`` or explicit ``path``)
      4. ``.env`` file (cwd → ``~/.viki/``)
      5. Environment variables (``VIKI_MODEL``, ``OLLAMA_HOST``, etc.)
      6. ``_FILE`` suffixed env vars (for secrets)
      7. ``cli_overrides`` dict
    """
    raw: dict[str, Any] = {}

    if path is None:
        found = _find_config_file()
    else:
        found = Path(path) if Path(path).is_file() else None

    if found is not None:
        file_raw = _load_config_file(found)
        file_raw = _resolve_includes(file_raw, found.parent)
        raw = _deep_merge(raw, file_raw)

    # .env file
    dotenv_raw = _load_dotenv(found.parent if found else None)
    if dotenv_raw:
        # Map flat env keys to nested sections using env map
        for env_k, env_v in dotenv_raw.items():
            if env_k in _ENV_MAP:
                section, field = _ENV_MAP[env_k]
                raw.setdefault(section, {})[field] = env_v
            else:
                raw.setdefault("llm", {})[env_k] = env_v

    # Environment variables (override .env)
    env_raw = _load_env()
    raw = _deep_merge(raw, env_raw)

    # CLI overrides (highest precedence) — supplied as flat keys
    if cli_overrides:
        raw = _deep_merge(raw, _flat_to_nested(cli_overrides))

    # Always convert remaining flat keys to nested before validation
    raw = _flat_to_nested(raw)

    return V2Config.model_validate(raw)


_config_singleton: V2Config | None = None


def get_config(
    path: str | Path | None = None, cli_overrides: dict[str, Any] | None = None
) -> V2Config:
    """Get or create the global ``V2Config`` singleton.

    Passing ``path`` or ``cli_overrides`` forces a reload.
    """
    global _config_singleton
    if _config_singleton is None or path is not None or cli_overrides:
        _config_singleton = load_config(path, cli_overrides=cli_overrides)
    return _config_singleton


def set_config(cfg: V2Config) -> None:
    """Set the config singleton (useful for testing)."""
    global _config_singleton
    _config_singleton = cfg


def reset_config() -> None:
    """Reset the config singleton (useful for testing)."""
    global _config_singleton
    _config_singleton = None


__all__ = [
    "V2Config",
    "LLMConfig",
    "MemoryConfig",
    "ToolsConfig",
    "UIConfig",
    "DataConfig",
    "load_config",
    "get_config",
    "set_config",
    "reset_config",
    "parse_cli_overrides",
    "watch_config",
]

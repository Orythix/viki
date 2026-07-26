"""Tests for V2 config module ported to core."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from viki.core.config import (
    LLMConfig,
    V2Config,
    get_config,
    load_config,
    parse_cli_overrides,
    set_config,
)


class TestV2ConfigDefaults:
    """Verify default configuration values."""

    def test_defaults(self):
        cfg = load_config()
        assert cfg.model == "google/gemma-4-e4b"
        assert cfg.lmstudio_url == "http://127.0.0.1:1234"
        assert cfg.temperature == 0.7
        assert cfg.max_steps == 10
        assert cfg.data_dir == "./data"
        assert cfg.theme == "dark"
        assert cfg.mcp_config_path == "config/mcp_servers.yaml"
        assert cfg.plugin_dirs == []
        assert cfg.tool_permissions == {}
        assert cfg.memory_max_turns == 50
        assert cfg.log_level == "INFO"

    def test_nested_access(self):
        """Verify section-level access."""
        cfg = load_config()
        assert cfg.llm.model == cfg.model
        assert cfg.llm.host == cfg.lmstudio_url
        assert cfg.llm.temperature == cfg.temperature
        assert cfg.llm.max_steps == cfg.max_steps
        assert cfg.tools.plugin_dirs == cfg.plugin_dirs
        assert cfg.memory.max_turns == cfg.memory_max_turns

    def test_no_shared_mutable_defaults(self):
        """Ensure no shared mutable defaults between instances."""
        cfg1 = load_config()
        cfg2 = load_config()
        cfg1.plugin_dirs.append("/custom")
        assert cfg2.plugin_dirs == []

    def test_frozen_immutable(self):
        """Config cannot be modified after creation."""
        cfg = load_config()
        with pytest.raises((TypeError, ValueError)):
            cfg.model = "new-model"
        with pytest.raises((TypeError, ValueError)):
            cfg.llm = LLMConfig()


class TestV2ConfigValidation:
    """Pydantic field validation."""

    def test_temperature_clamped(self):
        """Temperature is clamped to [0.0, 2.0]."""
        cfg = V2Config(llm={"temperature": 5.0})
        assert cfg.temperature == 2.0
        cfg = V2Config(llm={"temperature": -1.0})
        assert cfg.temperature == 0.0

    def test_max_steps_validation(self):
        """max_steps must be >= 1."""
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            V2Config(llm={"max_steps": 0})

    def test_host_strips_trailing_slash(self):
        """LM Studio host trailing slash is stripped."""
        cfg = V2Config(lmstudio_url="http://localhost:8080/")
        assert cfg.lmstudio_url == "http://localhost:8080"

    def test_memory_max_turns_minimum(self):
        """memory_max_turns is clamped to minimum 1."""
        cfg = V2Config(llm={"max_steps": 3}, memory={"max_turns": 0})
        assert cfg.memory_max_turns == 1


class TestV2ConfigJSON:
    """Loading config from JSON files."""

    def test_json_config(self, tmp_path: Path):
        config_file = tmp_path / "viki.json"
        data = {
            "model": "llama3:8b",
            "temperature": 0.3,
            "max_steps": 20,
            "plugin_dirs": ["/home/user/plugins"],
            "tool_permissions": {"shell": "ADMIN"},
        }
        config_file.write_text(json.dumps(data), encoding="utf-8")

        cfg = load_config(config_file)
        assert cfg.model == "llama3:8b"
        assert cfg.temperature == 0.3
        assert cfg.max_steps == 20
        assert cfg.plugin_dirs == ["/home/user/plugins"]
        assert cfg.tool_permissions == {"shell": "ADMIN"}

        # Lifted defaults still apply
        assert cfg.lmstudio_url == "http://127.0.0.1:1234"
        assert cfg.memory_max_turns == 50

    def test_json_nested_config(self, tmp_path: Path):
        """Config can use nested section keys."""
        config_file = tmp_path / "viki.json"
        data = {"llm": {"model": "nested-model"}, "tools": {"plugin_dirs": ["/p1", "/p2"]}}
        config_file.write_text(json.dumps(data), encoding="utf-8")
        cfg = load_config(config_file)
        assert cfg.model == "nested-model"
        assert cfg.plugin_dirs == ["/p1", "/p2"]

    def test_json_partial_override(self, tmp_path: Path):
        """Only specified fields are overridden; others keep defaults."""
        config_file = tmp_path / "viki.json"
        config_file.write_text(json.dumps({"model": "tiny"}), encoding="utf-8")
        cfg = load_config(config_file)
        assert cfg.model == "tiny"
        assert cfg.max_steps == 10  # default

    def test_json_case_sensitivity(self, tmp_path: Path):
        """Unknown keys in config file are ignored."""
        config_file = tmp_path / "viki.json"
        config_file.write_text(
            json.dumps({"Model": "llama3", "unknown_key": "value"}), encoding="utf-8"
        )
        cfg = load_config(config_file)
        assert cfg.model == "google/gemma-4-e4b"  # 'Model' != 'model'


class TestV2ConfigYAML:
    """Loading config from YAML files."""

    def test_yaml_config(self, tmp_path: Path):
        config_file = tmp_path / "viki.yaml"
        config_file.write_text(
            "model: llama3:8b\nmax_steps: 15\ndata_dir: /custom/data\n",
            encoding="utf-8",
        )
        cfg = load_config(config_file)
        assert cfg.model == "llama3:8b"
        assert cfg.max_steps == 15
        assert cfg.data_dir == "/custom/data"

    def test_yaml_yml_extension(self, tmp_path: Path):
        config_file = tmp_path / "viki.yml"
        config_file.write_text("model: codellama:7b\n", encoding="utf-8")
        cfg = load_config(config_file)
        assert cfg.model == "codellama:7b"

    def test_yaml_empty(self, tmp_path: Path):
        config_file = tmp_path / "viki.yaml"
        config_file.write_text("", encoding="utf-8")
        cfg = load_config(config_file)
        assert cfg.model == "google/gemma-4-e4b"  # defaults

    def test_yaml_include(self, tmp_path: Path):
        """YAML 'include' directive loads and merges additional files."""
        base_file = tmp_path / "base.yaml"
        base_file.write_text("model: from-base\n", encoding="utf-8")
        config_file = tmp_path / "viki.yaml"
        config_file.write_text(
            yaml.safe_dump({"include": "base.yaml", "max_steps": 30}), encoding="utf-8"
        )
        cfg = load_config(config_file)
        assert cfg.model == "from-base"
        assert cfg.max_steps == 30

    def test_yaml_include_deep_merge(self, tmp_path: Path):
        """Included values are deep-merged, not replaced."""
        base_file = tmp_path / "base.yaml"
        base_file.write_text("max_steps: 5\n", encoding="utf-8")
        config_file = tmp_path / "viki.yaml"
        config_file.write_text(
            yaml.safe_dump({"include": "base.yaml", "temperature": 0.9}), encoding="utf-8"
        )
        cfg = load_config(config_file)
        assert cfg.max_steps == 5  # from base
        assert cfg.temperature == 0.9  # from main file

    def test_yaml_include_list(self, tmp_path: Path):
        """include can be a list of paths."""
        a = tmp_path / "a.yaml"
        a.write_text("model: from-a\n", encoding="utf-8")
        b = tmp_path / "b.yaml"
        b.write_text("max_steps: 42\n", encoding="utf-8")
        config_file = tmp_path / "viki.yaml"
        config_file.write_text(yaml.safe_dump({"include": ["a.yaml", "b.yaml"]}), encoding="utf-8")
        cfg = load_config(config_file)
        assert cfg.model == "from-a"
        assert cfg.max_steps == 42


class TestV2ConfigEnvVars:
    """Environment variable overrides."""

    @patch.dict(os.environ, {}, clear=True)
    @patch.object(Path, "home", return_value=Path("/fake/home"))
    def test_env_var_override(self, mock_home, tmp_path: Path):
        with patch.dict(os.environ, {"VIKI_MODEL": "gpt4", "LMSTUDIO_URL": "http://localhost:8080"}):
            cfg = load_config()
            assert cfg.model == "gpt4"
            assert cfg.lmstudio_url == "http://localhost:8080"

    @patch.dict(os.environ, {}, clear=True)
    @patch.object(Path, "home", return_value=Path("/fake/home"))
    def test_env_beats_file(self, mock_home, tmp_path: Path):
        """Environment variables override values from config file."""
        config_file = tmp_path / "viki.json"
        config_file.write_text(
            json.dumps({"model": "llama3", "lmstudio_url": "http://file:1234"}), encoding="utf-8"
        )
        with patch.dict(os.environ, {"VIKI_MODEL": "env-model"}):
            cfg = load_config(config_file)
            assert cfg.model == "env-model"
            assert cfg.lmstudio_url == "http://file:1234"  # no env for this

    @patch.dict(os.environ, {}, clear=True)
    @patch.object(Path, "home", return_value=Path("/fake/home"))
    def test_env_file_suffix(self, mock_home, tmp_path: Path):
        """_FILE suffixed env vars load secrets from files."""
        secret_file = tmp_path / "model_secret.txt"
        secret_file.write_text("secret-model\n", encoding="utf-8")
        with patch.dict(os.environ, {"VIKI_MODEL_FILE": str(secret_file)}):
            cfg = load_config()
            assert cfg.model == "secret-model"

    @patch.dict(os.environ, {}, clear=True)
    @patch.object(Path, "home", return_value=Path("/fake/home"))
    def test_env_file_suffix_fallback(self, mock_home, tmp_path: Path):
        """_FILE env var takes precedence over regular env var."""
        secret_file = tmp_path / "host_secret.txt"
        secret_file.write_text("http://secret:1234", encoding="utf-8")
        with patch.dict(
            os.environ,
            {"LMSTUDIO_URL": "http://normal:1234", "LMSTUDIO_URL_FILE": str(secret_file)},
        ):
            cfg = load_config()
            assert cfg.lmstudio_url == "http://secret:1234"

    @patch.dict(os.environ, {}, clear=True)
    @patch.object(Path, "home", return_value=Path("/fake/home"))
    def test_env_file_missing_ignored(self, mock_home):
        """Missing _FILE paths are silently ignored."""
        with patch.dict(os.environ, {"VIKI_MODEL_FILE": "/nonexistent/path.txt"}):
            cfg = load_config()
            assert cfg.model == "google/gemma-4-e4b"  # default

    @patch.dict(os.environ, {}, clear=True)
    @patch.object(Path, "home", return_value=Path("/fake/home"))
    def test_coercion_from_env(self, mock_home):
        """String env values are coerced to the correct type."""
        with patch.dict(
            os.environ,
            {
                "VIKI_MODEL": "deepseek",
                "LMSTUDIO_URL": "http://other:1234",
                "VIKI_DATA_DIR": "/env/data",
                "VIKI_LOG_LEVEL": "DEBUG",
                "VIKI_MCP_CONFIG": "/env/mcp.yaml",
            },
        ):
            cfg = load_config()
            assert cfg.model == "deepseek"
            assert cfg.lmstudio_url == "http://other:1234"
            assert cfg.data_dir == "/env/data"
            assert cfg.log_level == "DEBUG"
            assert cfg.mcp_config_path == "/env/mcp.yaml"


class TestV2ConfigSearch:
    """Config file search behavior."""

    def test_cwd_config_json(self, tmp_path: Path):
        """JSON in current dir is found via search."""
        config_file = tmp_path / "viki.json"
        config_file.write_text(json.dumps({"model": "cwd-json"}), encoding="utf-8")
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmp_path)
            cfg = load_config()
            assert cfg.model == "cwd-json"
        finally:
            os.chdir(orig_cwd)

    def test_cwd_config_yaml(self, tmp_path: Path):
        """YAML in current dir is found via search."""
        config_file = tmp_path / "viki.yaml"
        config_file.write_text("model: cwd-yaml\n", encoding="utf-8")
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmp_path)
            cfg = load_config()
            assert cfg.model == "cwd-yaml"
        finally:
            os.chdir(orig_cwd)

    def test_config_subdir(self, tmp_path: Path):
        """Config in config/ subdirectory is found."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "viki.yaml"
        config_file.write_text("model: subdir-model\n", encoding="utf-8")
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmp_path)
            cfg = load_config()
            assert cfg.model == "subdir-model"
        finally:
            os.chdir(orig_cwd)


class TestV2ConfigDotEnv:
    """.env file loading."""

    @patch.object(Path, "home", return_value=Path("/fake/home"))
    def test_dotenv_loaded(self, mock_home, tmp_path: Path):
        """.env file in current dir is loaded."""
        env_file = tmp_path / ".env"
        env_file.write_text("VIKI_MODEL=dotenv-model\n", encoding="utf-8")
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmp_path)
            cfg = load_config()
            assert cfg.model == "dotenv-model"
        finally:
            os.chdir(orig_cwd)

    @patch.object(Path, "home", return_value=Path("/fake/home"))
    def test_dotenv_ignores_comments_and_blank(self, mock_home, tmp_path: Path):
        """.env comments and blank lines are ignored."""
        env_file = tmp_path / ".env"
        env_file.write_text("# This is a comment\n\nVIKI_TEMPERATURE=0.1\n", encoding="utf-8")
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmp_path)
            cfg = load_config()
            assert cfg.temperature == 0.1
        finally:
            os.chdir(orig_cwd)

    @patch.object(Path, "home", return_value=Path("/fake/home"))
    def test_env_beats_dotenv(self, mock_home, tmp_path: Path):
        """Environment variable beats .env file value."""
        env_file = tmp_path / ".env"
        env_file.write_text("VIKI_MODEL=dotenv-model\n", encoding="utf-8")
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmp_path)
            with patch.dict(os.environ, {"VIKI_MODEL": "env-model"}):
                cfg = load_config()
                assert cfg.model == "env-model"
        finally:
            os.chdir(orig_cwd)


class TestV2ConfigSingleton:
    """Global singleton behavior."""

    def teardown_method(self):
        set_config(V2Config())

    def test_singleton_persistence(self):
        set_config(V2Config(llm={"model": "singleton-model"}))
        cfg = get_config()
        assert cfg.model == "singleton-model"

    def test_get_config_caches(self):
        cfg1 = get_config()
        cfg2 = get_config()
        assert cfg1 is cfg2

    def test_get_config_force_reload(self, tmp_path: Path):
        """Passing path forces config reload."""
        config_file = tmp_path / "viki.json"
        config_file.write_text(json.dumps({"model": "reloaded"}), encoding="utf-8")
        cfg = get_config(config_file)
        assert cfg.model == "reloaded"

    def test_set_config_for_testing(self):
        test_cfg = V2Config(llm={"model": "test-model", "max_steps": 99})
        set_config(test_cfg)
        assert get_config().model == "test-model"
        assert get_config().max_steps == 99


class TestV2ConfigCoercion:
    """Type coercion and edge cases."""

    def test_temperature_string_coercion(self, tmp_path: Path):
        """Temperature can be a string in JSON and gets coerced to float."""
        config_file = tmp_path / "viki.json"
        config_file.write_text(json.dumps({"temperature": "0.5"}), encoding="utf-8")
        cfg = load_config(config_file)
        assert isinstance(cfg.temperature, float)
        assert cfg.temperature == 0.5

    def test_max_steps_string_coercion(self, tmp_path: Path):
        """max_steps as string in JSON is coerced to int."""
        config_file = tmp_path / "viki.json"
        config_file.write_text(json.dumps({"max_steps": "25"}), encoding="utf-8")
        cfg = load_config(config_file)
        assert isinstance(cfg.max_steps, int)
        assert cfg.max_steps == 25


class TestV2ConfigCLI:
    """CLI override parsing."""

    def test_cli_overrides_parsed(self):
        overrides, parsed = parse_cli_overrides(["--model", "cli-model", "--max-steps", "50"])
        assert overrides["model"] == "cli-model"
        assert overrides["max_steps"] == 50

    def test_cli_overrides_apply(self, tmp_path: Path):
        """CLI overrides beat file values."""
        config_file = tmp_path / "viki.json"
        config_file.write_text(json.dumps({"model": "file-model"}), encoding="utf-8")
        cfg = load_config(config_file, cli_overrides={"model": "cli-wins"})
        assert cfg.model == "cli-wins"

    def test_cli_generate_schema_flag(self):
        overrides, parsed = parse_cli_overrides(["--generate-schema"])
        assert parsed.generate_schema is True

    def test_cli_watch_flag(self):
        overrides, parsed = parse_cli_overrides(["--watch"])
        assert parsed.watch is True


class TestV2ConfigJSONSchema:
    """JSON Schema generation."""

    def test_generate_schema_file(self, tmp_path: Path):
        schema_path = tmp_path / "test_schema.json"
        result = V2Config.generate_schema_file(target=schema_path)
        assert result == str(schema_path)
        assert schema_path.is_file()
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        assert "$defs" in schema or "$ref" in schema
        assert schema.get("title") == "V2Config"

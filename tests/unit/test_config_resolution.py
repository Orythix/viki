"""Tests for configuration path resolution."""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))  # noqa: E402

from viki.config.resolve import get_soul_path  # noqa: E402


def test_get_soul_path_resolves_relative_to_settings_dir():
    """Soul path should be resolved relative to settings.yaml directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        settings_dir = Path(tmpdir) / "config"
        settings_dir.mkdir()
        settings_path = settings_dir / "settings.yaml"
        settings_path.write_text(
            """
system:
  owner:
    name: "Test"
soul_config: "./soul.yaml"
"""
        )
        soul_path = settings_dir / "soul.yaml"
        soul_path.write_text("system_prompt: 'Test'")

        result = get_soul_path(str(settings_path))
        assert result == str(soul_path)


def test_get_soul_path_fallback_to_personas():
    """Should fallback to personas/sovereign.yaml when soul.yaml doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        settings_dir = Path(tmpdir) / "config"
        settings_dir.mkdir()
        settings_path = settings_dir / "settings.yaml"
        settings_path.write_text(
            """
system:
  owner:
    name: "Test"
"""
        )
        # No soul.yaml, no persona - should default to personas/sovereign.yaml
        personas_dir = settings_dir / "personas"
        personas_dir.mkdir()
        sovereign_path = personas_dir / "sovereign.yaml"
        sovereign_path.write_text("system_prompt: 'Sovereign'")

        result = get_soul_path(str(settings_path))
        assert result == str(sovereign_path)


def test_get_soul_path_via_persona_env():
    """VIKI_PERSONA env var should select persona file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        settings_dir = Path(tmpdir) / "config"
        settings_dir.mkdir()
        settings_path = settings_dir / "settings.yaml"
        settings_path.write_text("system:\n  owner:\n    name: Test\n")
        personas_dir = settings_dir / "personas"
        personas_dir.mkdir()
        dev_path = personas_dir / "dev.yaml"
        dev_path.write_text("system_prompt: 'Dev'")

        os.environ["VIKI_PERSONA"] = "dev"
        try:
            result = get_soul_path(str(settings_path))
            assert result == str(dev_path)
        finally:
            del os.environ["VIKI_PERSONA"]

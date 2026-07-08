"""Filesystem locations for VIKI's non-code content bundled with the repo."""

import os
from pathlib import Path

# Repo layout: <root>/playbooks with the package at <root>/src/viki.
_REPO_ROOT = Path(__file__).resolve().parents[3]


def get_playbooks_dir() -> Path:
    """Directory holding playbook content; override with VIKI_PLAYBOOKS_DIR."""
    env = os.getenv("VIKI_PLAYBOOKS_DIR")
    if env:
        return Path(env).expanduser().resolve()
    return _REPO_ROOT / "playbooks"

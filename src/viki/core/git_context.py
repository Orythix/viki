"""
Optional git workspace snapshot for deliberation context.

Inspired by snapshot-style repo context in external CLI assistants; keeps prompts
grounded in branch/status without pulling the full TypeScript stack.
"""
from __future__ import annotations

import os
import subprocess
import time

_CACHE: dict[str, tuple[float, str]] = {}
_DEFAULT_TTL = 45.0
_GIT_TIMEOUT = 4.0


def _git_has_repo(workspace: str) -> bool:
    root = os.path.abspath(workspace)
    return os.path.isdir(os.path.join(root, ".git"))


def _run_git(workspace: str, *args: str) -> str:
    try:
        r = subprocess.run(
            ["git", "-C", workspace, *args],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
            check=False,
        )
        if r.returncode != 0:
            return ""
        return (r.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def get_git_workspace_snapshot(
    workspace_dir: str,
    max_status_chars: int = 2000,
    ttl_seconds: float = _DEFAULT_TTL,
) -> str:
    """
    Return a short markdown block with branch, truncated `git status --short`,
    and recent commits. Empty string if not a git repo, git missing, or errors.
    Cached per workspace for ttl_seconds to avoid per-message subprocess cost.
    """
    if not workspace_dir or not os.path.isdir(workspace_dir):
        return ""
    ws = os.path.abspath(workspace_dir)
    now = time.time()
    hit = _CACHE.get(ws)
    if hit and now - hit[0] < ttl_seconds:
        return hit[1]

    if not _git_has_repo(ws):
        _CACHE[ws] = (now, "")
        return ""

    branch = _run_git(ws, "branch", "--show-current") or "(unknown)"
    status = _run_git(ws, "--no-optional-locks", "status", "--short")
    if len(status) > max_status_chars:
        status = status[:max_status_chars] + "\n... (truncated)"
    log = _run_git(ws, "--no-optional-locks", "log", "--oneline", "-n", "5")

    lines = [
        "## Git snapshot (workspace)",
        "Snapshot at context build time; may be stale if you commit mid-session.",
        f"- **Current branch:** {branch}",
        "- **Status (`git status --short`):**",
        "```text",
        status or "(clean or no changes)",
        "```",
    ]
    if log:
        lines.extend(["- **Recent commits:**", "```text", log, "```"])

    block = "\n".join(lines)
    _CACHE[ws] = (now, block)
    return block


def clear_git_context_cache() -> None:
    """For tests."""
    _CACHE.clear()

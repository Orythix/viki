"""
Run one background evolution cycle without the full VIKI interactive UI.

Use from Windows Task Scheduler at logon (or cron on Linux) so lessons + Modelfile
can refresh even when the main CLI is not open.

Prerequisites:
  - Same as VIKI (Python env, Ollama for prompt-bake, network unless air-gap)
  - Set VIKI_DATA_DIR if your knowledge DB is not ./data

Environment:
  VIKI_SKIP_STARTUP_PULSE=1   (set by this script — avoids duplicate startup tasks)
  VIKI_BOOT_EVOLVE_FORCE=1    optional; if set, runs evolution even when forge.background_evolution_at_boot is false

Example (PowerShell, repo root):

  $env:VIKI_DATA_DIR = "D:\\VIKI\\data"
  python scripts/viki_headless_boot_evolve.py

See docs/VIKI_RUNBOOK.md § Background evolution and scripts/Register-VikiBootTask.ps1.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

os.environ.setdefault("VIKI_SKIP_STARTUP_PULSE", "1")


async def _amain() -> int:
    from dotenv import load_dotenv

    load_dotenv()
    force = os.environ.get("VIKI_BOOT_EVOLVE_FORCE", "").strip().lower() in ("1", "true", "yes")
    if force:
        os.environ["VIKI_BACKGROUND_EVOLUTION_AT_BOOT"] = "1"

    from viki.config.resolve import get_soul_path
    from viki.core.orchestrator import VIKIController

    settings_path = str(REPO_ROOT / "config" / "settings.yaml")
    soul_path = get_soul_path(settings_path)

    ctrl = VIKIController(settings_path, soul_path)
    try:
        try:
            ctrl.attach_mcp_skills_sync()
        except Exception:
            pass
        msg = await ctrl.run_boot_evolution_work(force=force)
        print(msg)
    finally:
        await ctrl.shutdown()
    return 0


def main() -> int:
    try:
        return asyncio.run(_amain())
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

"""Update system for VIKI — code, models, and plugins."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field

from viki.config.logger import viki_logger


@dataclass
class UpdateInfo:
    component: str
    current_version: str
    available_version: str
    update_available: bool
    update_command: str = ""
    changelog: str = ""


@dataclass
class UpdateSummary:
    updates: list[UpdateInfo] = field(default_factory=list)
    total_updates: int = 0
    total_size_mb: float = 0.0


class UpdateManager:
    """Check for and apply updates to VIKI, models, and plugins."""

    def __init__(self, config_dir: str | None = None):
        self.config_dir = config_dir or os.environ.get(
            "VIKI_CONFIG_DIR",
            os.path.join(os.getcwd(), "config"),
        )

    async def check_all(self) -> UpdateSummary:
        """Check all components for updates."""
        summary = UpdateSummary()

        # VIKI code updates (pip)
        viki_update = await self._check_pip_update()
        if viki_update:
            summary.updates.append(viki_update)

        # Model updates (Ollama)
        model_updates = await self._check_model_updates()
        summary.updates.extend(model_updates)

        summary.total_updates = len([u for u in summary.updates if u.update_available])
        return summary

    async def _check_pip_update(self) -> UpdateInfo | None:
        """Check if a newer VIKI version is available on PyPI or locally."""
        try:
            # Get current version
            current = ""
            try:
                import importlib.metadata

                current = importlib.metadata.version("viki-sdi")
            except Exception:
                current = "8.3.0"  # fallback

            # Try to check for latest version via pip index
            result = subprocess.run(
                [sys.executable, "-m", "pip", "index", "versions", "viki-sdi"],
                capture_output=True,
                text=True,
                timeout=15,
            )

            available = current
            update_available = False

            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if "Available versions:" in line:
                        versions = line.split(":", 1)[1].strip()
                        available = versions.split(",")[0].strip()

                        # Simple version comparison
                        if available != current:
                            update_available = True
                        break

            return UpdateInfo(
                component="VIKI",
                current_version=current,
                available_version=available if update_available else current,
                update_available=update_available,
                update_command=f'"{sys.executable}" -m pip install --upgrade viki-sdi',
            )
        except Exception as e:
            viki_logger.debug(f"Failed to check VIKI updates: {e}")
            return None

    async def _check_model_updates(self) -> list[UpdateInfo]:
        """Check if pulled Ollama models have updates."""
        updates = []
        try:
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode != 0:
                return []

            for line in result.stdout.strip().splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 2:
                    model_name = parts[0]
                    # Check if there's a newer version
                    # (Ollama doesn't have a clean "check update" API,
                    # so we check by attempting pull which idempotently updates)
                    updates.append(
                        UpdateInfo(
                            component=f"model:{model_name}",
                            current_version="local",
                            available_version="latest",
                            update_available=True,
                            update_command=f"ollama pull {model_name}",
                        )
                    )
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
            viki_logger.debug(f"Failed to check model updates: {e}")

        return updates

    async def apply_update(self, update: UpdateInfo, progress_callback=None) -> bool:
        """Apply a single update."""
        if not update.update_command:
            if progress_callback:
                progress_callback(f"No update command for {update.component}")
            return False

        if progress_callback:
            progress_callback(f"Updating {update.component}: {update.update_command}...")

        try:
            result = subprocess.run(
                update.update_command.split(),
                capture_output=True,
                text=True,
                timeout=300,
            )
            success = result.returncode == 0
            if progress_callback:
                if success:
                    progress_callback(f"[green]✓ {update.component} updated[/]")
                else:
                    progress_callback(
                        f"[red]✗ {update.component} update failed: {result.stderr[:200]}[/]"
                    )
            return success
        except subprocess.TimeoutExpired:
            if progress_callback:
                progress_callback(f"[red]✗ {update.component} update timed out[/]")
            return False
        except Exception as e:
            if progress_callback:
                progress_callback(f"[red]✗ {update.component} update error: {e}[/]")
            return False

    async def get_current_version(self) -> str:
        """Return the current VIKI version."""
        try:
            import importlib.metadata

            return importlib.metadata.version("viki-sdi")
        except Exception:
            return "8.3.0"

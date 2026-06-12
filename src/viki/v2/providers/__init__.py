"""System provider factory — returns the correct provider for the current platform."""

from __future__ import annotations

import sys


def create_provider():
    """Return the appropriate SystemProvider for the current platform."""
    platform = sys.platform.lower()
    if platform == "win32":
        from .windows import WindowsProvider

        return WindowsProvider()
    if platform == "linux":
        from .linux import LinuxProvider

        return LinuxProvider()
    if platform == "darwin":
        from .mac import MacProvider

        return MacProvider()
    raise RuntimeError(f"Unsupported platform: {platform}")

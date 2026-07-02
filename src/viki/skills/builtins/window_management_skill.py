"""
Windows desktop window manager skill.

`pypiwin32` (`win32gui`, `win32con`) is Windows-only. We import lazily so the
module can still be imported on non-Windows hosts (Linux/macOS CI runners,
Docker base images, etc.) without raising `ImportError`. Calls to
`execute()` on those platforms return a clear error string instead of
crashing the controller.
"""
from __future__ import annotations

import asyncio  # noqa: F401  (kept for backward compatibility)
import re  # noqa: F401  (kept for backward compatibility)
import sys
from typing import Any

from viki.config.logger import viki_logger
from viki.skills.base import BaseSkill

_WIN32_AVAILABLE = sys.platform == "win32"
_win32gui: Any = None
_win32con: Any = None
_win32_import_error: Exception | None = None


def _ensure_win32() -> bool:
    """Lazily import the win32 modules. Returns True on success."""
    global _win32gui, _win32con, _win32_import_error
    if _win32gui is not None and _win32con is not None:
        return True
    if not _WIN32_AVAILABLE:
        return False
    try:
        import win32con  # type: ignore
        import win32gui  # type: ignore

        _win32gui = win32gui
        _win32con = win32con
        return True
    except ImportError as e:
        _win32_import_error = e
        viki_logger.warning(
            "WindowManagerSkill: pywin32 not installed (%s). "
            'Install with `pip install -e ".[windows]"` to enable.',
            e,
        )
        return False


class WindowManagerSkill(BaseSkill):
    """
    Control Windows desktop windows.
    List open windows, focus, minimize, maximize, close specific applications.
    """

    @property
    def name(self) -> str:
        return "window_manager"

    @property
    def description(self) -> str:
        return "Manage desktop windows. Actions: list, focus(title), minimize(title), maximize(title), close(title)."

    @property
    def safety_tier(self) -> str:
        return "medium"

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "focus", "minimize", "maximize", "close", "restore"],
                    "description": "Window management action",
                },
                "title": {
                    "type": "string",
                    "description": "Partial title of the window to target (e.g., 'Notepad')",
                },
            },
            "required": ["action"],
        }

    def _get_windows(self) -> list[tuple[int, str]]:
        """Return list of (hwnd, title) for visible windows."""
        windows: list[tuple[int, str]] = []

        def callback(hwnd, _):
            if _win32gui.IsWindowVisible(hwnd):
                title = _win32gui.GetWindowText(hwnd)
                if title and title.strip():
                    windows.append((hwnd, title))

        _win32gui.EnumWindows(callback, None)
        return windows

    def _find_window(self, partial_title: str) -> int:
        """Find first window matching partial title (case-insensitive)."""
        if not partial_title:
            return 0

        target = partial_title.lower()
        for hwnd, title in self._get_windows():
            if target in title.lower():
                return hwnd
        return 0

    async def execute(self, params: dict[str, Any]) -> str:
        if not _ensure_win32():
            if not _WIN32_AVAILABLE:
                return (
                    f"WindowManagerSkill is Windows-only (current platform: {sys.platform}). "
                    "Use the equivalent OS-native tools on macOS / Linux."
                )
            return (
                "WindowManagerSkill requires pywin32. "
                'Install with `pip install -e ".[windows]"`.'
            )

        action = params.get("action")
        title_query = params.get("title")

        try:
            if action == "list":
                windows = self._get_windows()
                titles = [t for _, t in windows]
                return (
                    f"Open Windows ({len(titles)}):\n"
                    + "\n".join([f"- {t}" for t in titles[:20]])
                    + ("\n...(truncated)" if len(titles) > 20 else "")
                )

            if not title_query:
                return f"Error: '{action}' requires a 'title' parameter."

            hwnd = self._find_window(title_query)
            if not hwnd:
                return f"Error: No window found matching '{title_query}'."

            full_title = _win32gui.GetWindowText(hwnd)

            if action == "focus":
                try:
                    _win32gui.ShowWindow(hwnd, _win32con.SW_RESTORE)
                    _win32gui.SetForegroundWindow(hwnd)
                    return f"Focused window: '{full_title}'"
                except Exception as e:
                    return f"Failed to focus '{full_title}': {e}"

            elif action == "minimize":
                _win32gui.ShowWindow(hwnd, _win32con.SW_MINIMIZE)
                return f"Minimized '{full_title}'"

            elif action == "maximize":
                _win32gui.ShowWindow(hwnd, _win32con.SW_MAXIMIZE)
                return f"Maximized '{full_title}'"

            elif action == "restore":
                _win32gui.ShowWindow(hwnd, _win32con.SW_RESTORE)
                return f"Restored '{full_title}'"

            elif action == "close":
                _win32gui.PostMessage(hwnd, _win32con.WM_CLOSE, 0, 0)
                return f"Sent close signal to '{full_title}'"

            else:
                return f"Unknown action: {action}"

        except Exception as e:
            viki_logger.error(f"Window Manager error: {e}")
            return f"Window operation failed: {e}"

import win32gui
import win32con
import re
import asyncio
from typing import Dict, Any, List, Tuple
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger

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
                    "description": "Window management action"
                },
                "title": {
                    "type": "string",
                    "description": "Partial title of the window to target (e.g., 'Notepad')"
                }
            },
            "required": ["action"]
        }

    def _get_windows(self) -> List[Tuple[int, str]]:
        """Return list of (hwnd, title) for visible windows."""
        windows = []
        def callback(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title and title.strip():
                    windows.append((hwnd, title))
        win32gui.EnumWindows(callback, None)
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

    async def execute(self, params: Dict[str, Any]) -> str:
        action = params.get('action')
        title_query = params.get('title')

        try:
            if action == 'list':
                windows = self._get_windows()
                titles = [t for _, t in windows]
                return f"Open Windows ({len(titles)}):\n" + "\n".join([f"- {t}" for t in titles[:20]]) + ("\n...(truncated)" if len(titles) > 20 else "")

            if not title_query:
                return f"Error: '{action}' requires a 'title' parameter."

            # Find target window
            hwnd = self._find_window(title_query)
            if not hwnd:
                return f"Error: No window found matching '{title_query}'."

            full_title = win32gui.GetWindowText(hwnd)

            if action == 'focus':
                try:
                    # Generic way to force focus often requires attaching thread inputs or using brute force
                    # Simplest robust way is minimize then maximize sometimes, or specialized flags
                    # Here we try simple Show + SetForeground
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    win32gui.SetForegroundWindow(hwnd)
                    return f"Focused window: '{full_title}'"
                except Exception as e:
                     return f"Failed to focus '{full_title}': {e}"

            elif action == 'minimize':
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
                return f"Minimized '{full_title}'"

            elif action == 'maximize':
                win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
                return f"Maximized '{full_title}'"

            elif action == 'restore':
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                return f"Restored '{full_title}'"

            elif action == 'close':
                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                return f"Sent close signal to '{full_title}'"

            else:
                return f"Unknown action: {action}"

        except Exception as e:
            viki_logger.error(f"Window Manager error: {e}")
            return f"Window operation failed: {e}"

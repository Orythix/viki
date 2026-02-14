import subprocess
import os
import shutil
import webbrowser
import asyncio
import pyautogui
from typing import Dict, Any, Union
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger

class SystemControlSkill(BaseSkill):
    """
    Advanced System Control (Desktop Agent).
    Capabilities: App Launch, URL Open, Mouse Click, Keyboard Typing, Media Keys.
    """
    def __init__(self):
        # Comprehensive app whitelist — maps common names to executables
        self.whitelist = {
            'notepad': 'notepad.exe',
            'calc': 'calc.exe',
            'calculator': 'calc.exe',
            'cmd': 'cmd.exe',
            'command prompt': 'cmd.exe',
            'powershell': 'powershell.exe',
            'explorer': 'explorer.exe',
            'file explorer': 'explorer.exe',
            'taskmgr': 'taskmgr.exe',
            'task manager': 'taskmgr.exe',
            'chrome': 'chrome.exe',
            'google chrome': 'chrome.exe',
            'firefox': 'firefox.exe',
            'edge': 'msedge.exe',
            'microsoft edge': 'msedge.exe',
            'vscode': 'code',
            'vs code': 'code',
            'visual studio code': 'code',
            'terminal': 'wt.exe',
            'windows terminal': 'wt.exe',
            'paint': 'mspaint.exe',
            'snipping tool': 'snippingtool.exe',
            'settings': 'ms-settings:',
            'spotify': 'spotify.exe',
            'vlc': 'vlc.exe',
            'discord': 'discord.exe',
            'slack': 'slack.exe',
            'teams': 'teams.exe',
            'word': 'winword.exe',
            'excel': 'excel.exe',
            'powerpoint': 'powerpnt.exe',
            'outlook': 'outlook.exe',
        }
        # Fail-safe: Moving mouse to corner will throw exception
        pyautogui.FAILSAFE = True

    @property
    def name(self) -> str:
        return "system_control"

    @property
    def description(self) -> str:
        return (
            "Control the OS. "
            "Actions: open_app(name), open_url(url), click(x,y), "
            "type(text), press(key), scroll(amount), hotkey(keys)."
        )

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["open_app", "open_url", "click", "type", "press", "scroll", "hotkey"],
                    "description": "The system control action to perform"
                },
                "name": {"type": "string", "description": "App name to open (for open_app)"},
                "url": {"type": "string", "description": "URL to open (for open_url)"},
                "text": {"type": "string", "description": "Text to type (for type)"},
                "key": {"type": "string", "description": "Key to press (for press, e.g. 'enter', 'tab')"},
                "x": {"type": "integer", "description": "X coordinate (for click)"},
                "y": {"type": "integer", "description": "Y coordinate (for click)"},
                "amount": {"type": "integer", "description": "Scroll amount (for scroll)"},
                "keys": {"type": "string", "description": "Hotkey combo (for hotkey, e.g. 'ctrl+c')"}
            },
            "required": ["action"]
        }

    async def execute(self, params: Dict[str, Any]) -> str:
        action = params.get('action')
        
        # Support legacy params directly (no 'action' key)
        if not action:
            if 'app_name' in params or 'name' in params:
                return await self._open_app(params.get('app_name') or params.get('name'))
            if 'url' in params:
                return self._open_url(params['url'])
            if 'text' in params:
                return await self._type_text(params['text'])
            if 'key' in params:
                return await self._press_key(params['key'])
            return "Error: No action or recognizable parameters provided."

        # Explicit actions
        if action == 'open_app':
            return await self._open_app(params.get('name', ''))
        if action == 'open_url':
            return self._open_url(params.get('url', ''))
        
        try:
            if action == 'click':
                x = params.get('x')
                y = params.get('y')
                if x is not None and y is not None:
                    await asyncio.to_thread(pyautogui.click, x=int(x), y=int(y))
                    return f"Clicked at ({x}, {y})."
                return "Error: Coordinates x, y required for click."
            
            if action == 'type':
                return await self._type_text(params.get('text', ''))
            
            if action == 'press':
                return await self._press_key(params.get('key', ''))

            if action == 'hotkey':
                keys = params.get('keys', [])
                if isinstance(keys, str):
                    keys = [k.strip() for k in keys.split('+')]
                if keys:
                    await asyncio.to_thread(pyautogui.hotkey, *keys)
                    return f"Pressed hotkey: {'+'.join(keys)}."
                return "Error: 'keys' required (e.g., ['ctrl', 'c'] or 'ctrl+c')."

            if action == 'scroll':
                amount = params.get('amount', 0)
                await asyncio.to_thread(pyautogui.scroll, int(amount))
                return f"Scrolled by {amount}."
                
        except Exception as e:
            return f"Desktop action failed: {e}"

        return f"Unknown action: '{action}'. Supported: open_app, open_url, click, type, press, hotkey, scroll."

    async def _open_app(self, app_name: str) -> str:
        if not app_name:
            return "Error: No app name provided."
        
        app_clean = app_name.lower().strip()
        
        # 1. Check whitelist
        target = self.whitelist.get(app_clean)
        if target:
            try:
                if target.startswith('ms-settings:'):
                    os.startfile(target)
                else:
                    subprocess.Popen(target, shell=True)
                return f"Launched {app_name}."
            except Exception as e:
                return f"Error launching {app_name}: {e}"
        
        # 2. Try direct execution (for apps in PATH)
        exe_name = app_clean if app_clean.endswith('.exe') else f"{app_clean}.exe"
        if shutil.which(exe_name):
            try:
                subprocess.Popen(exe_name, shell=True)
                return f"Launched {app_name}."
            except Exception as e:
                return f"Error launching {app_name}: {e}"
        
        # 3. Try Windows Start Menu search via shell
        try:
            subprocess.Popen(f'start "" "{app_name}"', shell=True)
            return f"Attempted to launch {app_name} via Windows search."
        except Exception as e:
            return f"Could not find or launch '{app_name}': {e}"

    async def _type_text(self, text: str) -> str:
        if not text:
            return "Error: No text provided."
        await asyncio.to_thread(pyautogui.write, text, interval=0.03)
        return f"Typed: {text}"

    async def _press_key(self, key: str) -> str:
        if not key:
            return "Error: No key specified."
        await asyncio.to_thread(pyautogui.press, key)
        return f"Pressed: {key}"

    def _open_url(self, url: str) -> str:
        if not url:
            return "Error: No URL provided."
        # ABSOLUTE BACKGROUND RULE:
        # If the user says "do it in the background", we must NOT open a visible browser.
        # So we restrict open_url ONLY to non-http protocols (like spotify:, steam:, etc)
        if url.startswith("http:") or url.startswith("https:"):
            return "Error: Visible browser launch disabled by user preference. Use the 'research' skill to read content invisibly."
            
        try:
            webbrowser.open(url)
            return f"Launched protocol {url}."
        except Exception as e:
            return f"Error opening URL: {e}"

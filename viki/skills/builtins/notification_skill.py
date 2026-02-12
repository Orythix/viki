import asyncio
import subprocess
from typing import Dict, Any
from viki.skills.base import BaseSkill

class NotificationSkill(BaseSkill):
    """
    Send Windows Toast Notifications.
    """
    @property
    def name(self) -> str:
        return "notification"

    @property
    def description(self) -> str:
        return "Send a system notification. Action: notify(title, message)."

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Title of the notification"
                },
                "message": {
                    "type": "string",
                    "description": "Body text of the notification"
                }
            },
            "required": ["message"]
        }

    async def execute(self, params: Dict[str, Any]) -> str:
        title = params.get('title', 'VIKI Notification')
        message = params.get('message', '') # Required
        
        if not message:
            return "Error: Message required."

        # Reliable BalloonTip method
        ps_script = f"""
        Add-Type -AssemblyName System.Windows.Forms
        $notify = New-Object System.Windows.Forms.NotifyIcon
        $notify.Icon = [System.Drawing.SystemIcons]::Information
        $notify.BalloonTipTitle = "{title}"
        $notify.BalloonTipText = "{message}"
        $notify.Visible = $True
        $notify.ShowBalloonTip(5000)
        Start-Sleep -Seconds 1 # Ensure icon stays momentarily
        $notify.Dispose()
        """
        
        try:
            import base64
            # PowerShell requires UTF-16LE encoding for Base64 commands
            encoded_cmd = base64.b64encode(ps_script.encode('utf_16_le')).decode('utf-8')
            
            process = await asyncio.create_subprocess_exec(
                "powershell", "-NoProfile", "-EncodedCommand", encoded_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            return f"Notification sent: {title} - {message}"
        except Exception as e:
            return f"Notification failed: {e}"

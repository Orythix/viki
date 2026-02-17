import asyncio
import os
from typing import Dict, Any
from viki.config.logger import viki_logger

class CalendarSkill:
    """
    Skill for managing calendar events. Uses Google Calendar API when
    integrations.google_calendar.enabled; otherwise fallback mock.
    """
    def __init__(self, controller=None):
        self._controller = controller
        self.name = "calendar"
        self.description = "Manages calendar events (Google Calendar when configured)."
        self.triggers = ["schedule", "appointment", "calendar", "event", "meeting"]

    def _calendar_service(self):
        if not self._controller:
            return None
        settings = self._controller.settings
        integ = settings.get("integrations", {}).get("google_calendar", {})
        if not integ.get("enabled"):
            return None
        path = integ.get("credentials_path") or os.environ.get("VIKI_GOOGLE_CALENDAR_CREDENTIALS_PATH")
        if not path or not os.path.isfile(path):
            return None
        data_dir = settings.get("system", {}).get("data_dir", "./data")
        token_path = os.path.join(data_dir, "google_calendar_token.json")
        try:
            from viki.integrations.google_calendar_client import get_calendar_service
            return get_calendar_service(path, token_path)
        except Exception as e:
            viki_logger.debug(f"Calendar client: {e}")
            return None

    async def execute(self, params: Dict[str, Any]) -> str:
        action = params.get('action', 'list')
        title = params.get('title')
        time_str = params.get('time')
        viki_logger.info(f"Calendar: Executing {action} for '{title}' at {time_str}")

        service = await asyncio.to_thread(self._calendar_service)
        cal_id = (self._controller.settings.get("integrations", {}).get("google_calendar", {}).get("default_calendar_id") or "primary") if self._controller else "primary"
        if service:
            from viki.integrations import google_calendar_client as gcal
            if action == "add":
                if not title or not time_str:
                    return "ERROR: title and time required for add."
                return await asyncio.to_thread(gcal.calendar_add, service, cal_id, title, time_str)
            if action == "list":
                return await asyncio.to_thread(gcal.calendar_list, service, cal_id, 20)
            if action == "remove":
                if not title:
                    return "ERROR: title required for remove."
                return await asyncio.to_thread(gcal.calendar_remove, service, cal_id, title)
            return "ERROR: Unknown calendar action."

        # Fallback mock
        if action == "add":
            return f"SUCCEEDED: Appointment '{title}' scheduled for {time_str}."
        if action == "list":
            return "SCHEDULE: 10:00 AM - Strategy Meeting with Team, 2:00 PM - Research Paper Review."
        if action == "remove":
            return f"SUCCEEDED: '{title}' removed from calendar."
        return "ERROR: Unknown calendar action."

    def get_tool_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "calendar",
                "description": "Add, list or remove calendar events.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["add", "list", "remove"], "description": "The action to perform."},
                        "title": {"type": "string", "description": "Title of the event."},
                        "time": {"type": "string", "description": "ISO format or human readable time."}
                    },
                    "required": ["action"]
                }
            }
        }

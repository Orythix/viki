"""
Google Calendar API client for VIKI. Used by CalendarSkill when integrations.google_calendar.enabled.
Requires: google-auth, google-auth-oauthlib, google-api-python-client.
"""
import os
from typing import Any, Dict, List, Optional
from datetime import datetime

def get_calendar_service(credentials_path: str, token_path: str):
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        return None
    SCOPES = ["https://www.googleapis.com/auth/calendar.events", "https://www.googleapis.com/auth/calendar.readonly"]
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_path):
                return None
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
        os.makedirs(os.path.dirname(token_path) or ".", exist_ok=True)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return build("calendar", "v3", credentials=creds)


def calendar_list(service, calendar_id: str = "primary", max_results: int = 20) -> str:
    if not service:
        return "Google Calendar not configured."
    try:
        from datetime import timezone
        now = datetime.now(timezone.utc).isoformat()
        events = service.events().list(calendarId=calendar_id, timeMin=now, maxResults=max_results, singleEvents=True, orderBy="startTime").execute()
        items = events.get("items", [])
        if not items:
            return "SCHEDULE: No upcoming events."
        lines = []
        for e in items:
            start = e.get("start", {}).get("dateTime") or e.get("start", {}).get("date", "?")
            title = e.get("summary", "(no title)")
            lines.append(f"- {start[:16]} - {title}")
        return "SCHEDULE (Google Calendar):\n" + "\n".join(lines)
    except Exception as e:
        return f"Calendar list error: {e}"


def calendar_add(service, calendar_id: str, title: str, time_str: str) -> str:
    if not service:
        return "Google Calendar not configured."
    try:
        start = time_str.replace("Z", "+00:00") if "T" in time_str else time_str + "T09:00:00"
        # Default 1hr duration: if start has time, add 1 hour to end (simplified string hack for ISO)
        end = start
        if "T" in start and ":" in start:
            from datetime import datetime, timezone, timedelta
            try:
                dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                end_dt = dt + timedelta(hours=1)
                end = end_dt.isoformat()
            except ValueError:
                end = start
        event = {"summary": title, "start": {"dateTime": start, "timeZone": "UTC"}, "end": {"dateTime": end, "timeZone": "UTC"}}
        service.events().insert(calendarId=calendar_id, body=event).execute()
        return f"SUCCEEDED: Event '{title}' scheduled for {time_str}."
    except Exception as e:
        return f"Calendar add error: {e}"


def calendar_remove(service, calendar_id: str, title: str) -> str:
    if not service:
        return "Google Calendar not configured."
    try:
        events = service.events().list(calendarId=calendar_id, q=title, singleEvents=True).execute()
        for e in events.get("items", []):
            if title.lower() in (e.get("summary") or "").lower():
                service.events().delete(calendarId=calendar_id, eventId=e["id"]).execute()
                return f"SUCCEEDED: '{title}' removed from calendar."
        return f"No event found matching '{title}'."
    except Exception as e:
        return f"Calendar remove error: {e}"

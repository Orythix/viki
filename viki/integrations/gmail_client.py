"""
Gmail API client for VIKI. Used by EmailSkill when integrations.gmail.enabled.
Requires: google-auth, google-auth-oauthlib, google-api-python-client.
Credentials: VIKI_GMAIL_CREDENTIALS_PATH or settings integrations.gmail.credentials_path.
"""
import os
from typing import Any, Dict, List, Optional

def get_gmail_service(credentials_path: str, token_path: str):
    """Build Gmail API service from credentials JSON and token cache."""
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        return None
    SCOPES = ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.send", "https://www.googleapis.com/auth/gmail.modify"]
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
    return build("gmail", "v1", credentials=creds)


def gmail_read(service, max_results: int = 10) -> str:
    if not service:
        return "Gmail not configured."
    try:
        results = service.users().messages().list(userId="me", maxResults=max_results).execute()
        messages = results.get("messages", [])
        if not messages:
            return "INBOX: No recent messages."
        lines = []
        for m in messages[:max_results]:
            msg = service.users().messages().get(userId="me", id=m["id"]).execute()
            payload = msg.get("payload", {})
            headers = {h["name"]: h["value"] for h in payload.get("headers", [])}
            subject = headers.get("Subject", "(no subject)")
            from_ = headers.get("From", "?")
            snippet = msg.get("snippet", "")[:200]
            lines.append(f"- From: {from_} | Subject: {subject}\n  {snippet}")
        return "INBOX (Gmail):\n" + "\n".join(lines)
    except Exception as e:
        return f"Gmail read error: {e}"


def gmail_send(service, to: str, subject: str, body: str) -> str:
    if not service:
        return "Gmail not configured."
    try:
        from email.mime.text import MIMEText
        import base64
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject or "(no subject)"
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return f"SUCCEEDED: Email sent to {to} regarding '{subject}'."
    except Exception as e:
        return f"Gmail send error: {e}"

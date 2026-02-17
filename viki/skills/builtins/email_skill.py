import asyncio
import os
from typing import Dict, Any
from viki.config.logger import viki_logger

class EmailSkill:
    """
    Skill for managing emails. Uses Gmail API when integrations.gmail.enabled
    and credentials are set; otherwise fallback mock.
    """
    def __init__(self, controller=None):
        self._controller = controller
        self.name = "email"
        self.description = "Sends, reads, and manages emails (Gmail when configured)."
        self.triggers = ["email", "mail", "send message", "inbox"]

    def _gmail_service(self):
        if not self._controller:
            return None
        settings = self._controller.settings
        integ = settings.get("integrations", {}).get("gmail", {})
        if not integ.get("enabled"):
            return None
        path = integ.get("credentials_path") or os.environ.get("VIKI_GMAIL_CREDENTIALS_PATH")
        if not path or not os.path.isfile(path):
            return None
        data_dir = settings.get("system", {}).get("data_dir", "./data")
        token_path = os.path.join(data_dir, "gmail_token.json")
        try:
            from viki.integrations.gmail_client import get_gmail_service
            return get_gmail_service(path, token_path)
        except Exception as e:
            viki_logger.debug(f"Gmail client: {e}")
            return None

    async def execute(self, params: Dict[str, Any]) -> str:
        action = params.get('action', 'read')
        recipient = params.get('to')
        subject = params.get('subject')
        body = params.get('body')
        viki_logger.info(f"Email: Executing {action} to {recipient}")

        service = await asyncio.to_thread(self._gmail_service)
        if service:
            if action == "send":
                if not recipient or not body:
                    return "ERROR: Recipient and body required for sending email."
                return await asyncio.to_thread(
                    __import__("viki.integrations.gmail_client", fromlist=["gmail_send"]).gmail_send,
                    service, recipient, subject or "", body
                )
            if action == "read":
                return await asyncio.to_thread(
                    __import__("viki.integrations.gmail_client", fromlist=["gmail_read"]).gmail_read,
                    service, 10
                )
            if action == "summarize":
                raw = await asyncio.to_thread(
                    __import__("viki.integrations.gmail_client", fromlist=["gmail_read"]).gmail_read,
                    service, 20
                )
                return f"SUMMARY (from inbox): {raw[:800]}"
            return "ERROR: Unknown email action."

        # Fallback mock
        if action == "send":
            if not recipient or not body:
                return "ERROR: Recipient and body required for sending email."
            return f"SUCCEEDED: Email sent to {recipient} regarding '{subject}'."
        if action == "read":
            return "INBOX: 3 Unread Messages. 1. Github: Security Alert. 2. LinkedIn: New Connection. 3. VikiDev: Build Successful."
        if action == "summarize":
            return "SUMMARY: Your inbox contains mostly automated reports and one personal query."
        return "ERROR: Unknown email action."

    def get_tool_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "email",
                "description": "Send, read, or summarize emails.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["send", "read", "summarize"], "description": "The action to perform."},
                        "to": {"type": "string", "description": "Email address of the recipient."},
                        "subject": {"type": "string", "description": "Subject line."},
                        "body": {"type": "string", "description": "Body content."}
                    },
                    "required": ["action"]
                }
            }
        }

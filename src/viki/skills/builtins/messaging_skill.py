"""
Unified messaging skill (CLAWDIS-style). Single interface for Telegram, Discord, Slack, WhatsApp.
Delegates to controller bridges when present; otherwise uses env-configured API tokens for send.
"""
import os
import asyncio
from typing import Dict, Any
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger


class UnifiedMessagingSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "messaging"

    @property
    def description(self) -> str:
        return (
            "Send or read messages across channels. "
            "Actions: send(channel, recipient, text), read(channel). "
            "Channels: telegram, discord, slack, whatsapp."
        )

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["send", "read", "list_channels"], "description": "Action to perform."},
                "channel": {"type": "string", "enum": ["telegram", "discord", "slack", "whatsapp"], "description": "Channel name."},
                "recipient": {"type": "string", "description": "Chat ID, channel ID, or user ID for send."},
                "text": {"type": "string", "description": "Message text for send."},
            },
            "required": ["action"],
        }

    def __init__(self, controller=None):
        self._controller = controller

    async def _send_telegram(self, recipient: str, text: str) -> str:
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if not token:
            return "Telegram not configured: set TELEGRAM_BOT_TOKEN."
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                async with session.post(url, json={"chat_id": recipient, "text": text}) as resp:
                    if resp.status == 200:
                        return "SUCCEEDED: Message sent via Telegram."
                    return f"Telegram API error: {resp.status} {await resp.text()}"
        except Exception as e:
            return f"Telegram send error: {e}"

    async def execute(self, params: Dict[str, Any]) -> str:
        action = params.get("action", "send")
        channel = (params.get("channel") or "").lower()
        recipient = params.get("recipient")
        text = params.get("text") or ""

        if action == "list_channels":
            out = []
            if os.environ.get("TELEGRAM_BOT_TOKEN"):
                out.append("telegram")
            if os.environ.get("DISCORD_BOT_TOKEN"):
                out.append("discord")
            if os.environ.get("SLACK_BOT_TOKEN") or os.environ.get("SLACK_USER_TOKEN"):
                out.append("slack")
            if os.environ.get("WHATSAPP_TOKEN"):
                out.append("whatsapp")
            return "Channels available: " + (", ".join(out) if out else "none (set tokens in env)")

        if action == "read":
            return f"Use the {channel} bridge for live conversations. Inbox read not implemented for {channel}."

        if action == "send":
            if not channel or not text:
                return "ERROR: channel and text required for send."
            if not recipient and channel != "slack":
                return "ERROR: recipient required for send (chat_id, channel_id, or user id)."
            # Delegate to bridge if controller has it
            bridge = getattr(self._controller, channel, None) if self._controller else None
            if bridge and hasattr(bridge, "send_to"):
                return await bridge.send_to(recipient, text)
            # Fallback: direct API
            if channel == "telegram":
                return await self._send_telegram(recipient or "", text)
            if channel == "discord":
                return "Discord: set up Discord bridge or use webhook URL."
            if channel == "slack":
                return "Slack: set up Slack bridge and recipient channel."
            if channel == "whatsapp":
                return "WhatsApp: set up WhatsApp Business API."
            return f"Unknown channel: {channel}."

        return "ERROR: Unknown action. Use send, read, or list_channels."

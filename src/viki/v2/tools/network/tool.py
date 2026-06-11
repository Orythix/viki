"""NetworkTool — WiFi, IP, DNS, diagnostics."""

from __future__ import annotations

from ...core.permission_manager import PermissionTier
from ...providers.base import SystemProvider
from ..base import BaseTool, ToolResult


class NetworkTool(BaseTool):
    name = "network"
    description = "Retrieves network configuration, WiFi details, and performs diagnostics."
    capabilities = [
        "get_wifi_password",
        "get_ip_address",
        "get_dns_info",
        "ping",
        "traceroute",
        "get_network_adapters",
    ]
    permission_tier = PermissionTier.ELEVATED
    examples = [
        "What is my WiFi password?",
        "Show my wireless key",
        "What is my IP address?",
        "Ping google.com",
        "Show DNS configuration",
        "What network am I connected to?",
    ]
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "wifi_password",
                    "ip_address",
                    "dns",
                    "ping",
                    "traceroute",
                    "adapters",
                    "info",
                ],
            },
            "target": {
                "type": "string",
                "description": "SSID for WiFi or host for ping",
            },
        },
        "required": ["action"],
    }

    def __init__(self, provider: SystemProvider | None = None):
        self.provider = provider

    async def execute(self, params: dict, provider=None) -> ToolResult:
        p = provider or self.provider
        if not p:
            return ToolResult(success=False, error="No system provider available")

        action = params.get("action", "info")
        try:
            if action == "wifi_password":
                data = await p.get_wifi_password(params.get("target"))
            elif action == "ip_address":
                data = await p.get_ip_address()
            elif action == "ping":
                host = params.get("target", "8.8.8.8")
                data = await p.ping(host)
            elif action == "info":
                data = await p.get_network_info()
            else:
                data = await p.get_network_info()
            return ToolResult(success=True, data=data)
        except Exception as e:
            return ToolResult(success=False, error=str(e), error_type="execution_failed")

"""Formats tool results into user response."""

from __future__ import annotations

from typing import Any

from ..tools.base import ToolResult


class ResponseGenerator:
    """Formats tool execution results into user-friendly responses."""

    def format_result(self, result: ToolResult, tool_name: str = "") -> str:
        """Format a tool result for display."""
        if not result.success:
            return f"❌ Error ({tool_name}): {result.error}"

        data = result.data
        if data is None:
            return f"✅ {tool_name}: Completed (no data)"

        # Format based on tool type
        if tool_name == "system":
            return self._format_system(data)
        elif tool_name == "network":
            return self._format_network(data)
        else:
            return self._format_generic(data, tool_name)

    def _format_system(self, data: dict) -> str:
        lines = ["🖥️ **System Information**"]
        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(f"\n**{key.title()}:**")
                for k, v in value.items():
                    lines.append(f"  {k}: {v}")
            elif isinstance(value, list):
                lines.append(f"\n**{key.title()}:** ({len(value)} items)")
                for item in value[:5]:
                    lines.append(f"  - {item}")
                if len(value) > 5:
                    lines.append(f"  ... and {len(value) - 5} more")
            else:
                lines.append(f"{key}: {value}")
        return "\n".join(lines)

    def _format_network(self, data: dict) -> str:
        lines = ["🌐 **Network Information**"]
        for key, value in data.items():
            if key == "password" and value:
                lines.append(f"Password: `{value}`")
            elif isinstance(value, dict):
                lines.append(f"\n**{key.title()}:**")
                for k, v in value.items():
                    lines.append(f"  {k}: {v}")
            elif isinstance(value, list):
                lines.append(f"\n**{key.title()}:** ({len(value)} items)")
                for item in value[:3]:
                    lines.append(f"  - {item}")
            else:
                lines.append(f"{key}: {value}")
        return "\n".join(lines)

    def _format_generic(self, data: Any, tool_name: str) -> str:
        import json

        return f"✅ **{tool_name}**:\n```json\n{json.dumps(data, indent=2, default=str)}\n```"

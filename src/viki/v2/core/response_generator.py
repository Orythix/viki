"""Formats tool results into user response."""

from __future__ import annotations


class ResponseGenerator:
    def format_result(self, result, tool_name: str = "") -> str:
        if not result.success:
            return f"I encountered an error: {result.error}"
        return str(result.data)

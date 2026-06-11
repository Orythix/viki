"""Builds LLM context from memory + tools."""

from __future__ import annotations


class ContextBuilder:
    def __init__(self, tool_registry=None):
        self.tool_registry = tool_registry

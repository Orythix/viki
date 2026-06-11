"""Core agent — main LLM session + ReAct loop."""

from __future__ import annotations


class CoreAgent:
    def __init__(self, tool_registry=None, intent_analyzer=None, permission_manager=None):
        self.tool_registry = tool_registry
        self.intent_analyzer = intent_analyzer
        self.permission_manager = permission_manager

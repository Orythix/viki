"""Tool execution with timeout, sandbox, capture."""

from __future__ import annotations


class ExecutionEngine:
    def __init__(self, tool_registry=None, permission_manager=None):
        self.tool_registry = tool_registry
        self.permission_manager = permission_manager

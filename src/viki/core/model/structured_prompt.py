"""Structured prompt builder for LLM interactions."""

from __future__ import annotations


class StructuredPrompt:
    def __init__(self, request: str, messages: list[dict[str, str]] = None):
        self.request = request
        self.messages = messages or []
        self.identity = ""
        self.cognitive_instructions = ""
        self.context = ""

    def set_identity(self, identity: str):
        self.identity = identity

    def add_cognitive(self, instruction: str):
        self.cognitive_instructions += f"\n- {instruction}"

    def add_context(self, context: str):
        self.context = context

    def build(self) -> list[dict[str, str]]:
        system_content = (
            f"{self.identity}\n\nCOGNITIVE PROTOCOLS:{self.cognitive_instructions}\n\n"
            f"CONTEXT:\n{self.context}"
        )
        final_messages = [{"role": "system", "content": system_content}]
        final_messages.extend(self.messages)
        final_messages.append({"role": "user", "content": self.request})
        return final_messages

"""
Obsidian vault skill: search, read, create, refactor notes. Config: obsidian.vault_path in settings.
"""
import os
import re
from typing import Dict, Any
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger


class ObsidianSkill(BaseSkill):
    def __init__(self, controller=None):
        self._controller = controller

    @property
    def name(self) -> str:
        return "obsidian"

    @property
    def description(self) -> str:
        return "Work with Obsidian vault: list, search, read_note, create_note. Set obsidian.vault_path in settings."

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "search", "read_note", "create_note"], "description": "Action."},
                "path": {"type": "string", "description": "Note path or filename."},
                "content": {"type": "string", "description": "Content for create_note."},
                "query": {"type": "string", "description": "Search query."},
            },
            "required": ["action"],
        }

    def _vault_path(self) -> str:
        if not self._controller:
            return ""
        return (self._controller.settings.get("obsidian") or {}).get("vault_path") or os.environ.get("VIKI_OBSIDIAN_VAULT", "")

    async def execute(self, params: Dict[str, Any]) -> str:
        action = (params.get("action") or "list").lower()
        vault = self._vault_path()
        if not vault or not os.path.isdir(vault):
            return "Obsidian vault not configured: set obsidian.vault_path or VIKI_OBSIDIAN_VAULT."

        if action == "list":
            try:
                names = [f for f in os.listdir(vault) if f.endswith(".md")]
                return "Notes:\n" + "\n".join(names[:50])
            except Exception as e:
                return f"List error: {e}"

        if action == "search":
            query = (params.get("query") or "").lower()
            if not query:
                return "Provide query for search."
            try:
                results = []
                for root, _, files in os.walk(vault):
                    for f in files:
                        if not f.endswith(".md"):
                            continue
                        path = os.path.join(root, f)
                        with open(path, "r", encoding="utf-8", errors="ignore") as file:
                            text = file.read()
                        if query in text.lower():
                            results.append(os.path.relpath(path, vault))
                return "Search results:\n" + "\n".join(results[:30]) if results else "No matches."
            except Exception as e:
                return f"Search error: {e}"

        if action == "read_note":
            path = params.get("path") or ""
            if not path:
                return "Provide path for read_note."
            full = os.path.join(vault, path)
            if not os.path.isfile(full):
                return f"Note not found: {path}"
            try:
                with open(full, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()[:8000]
            except Exception as e:
                return f"Read error: {e}"

        if action == "create_note":
            path = params.get("path") or ""
            content = params.get("content") or ""
            if not path:
                return "Provide path and content for create_note."
            if not path.endswith(".md"):
                path += ".md"
            full = os.path.join(vault, path)
            try:
                os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
                with open(full, "w", encoding="utf-8") as f:
                    f.write(content)
                return f"Created note: {path}"
            except Exception as e:
                return f"Create error: {e}"

        return "Unknown action. Use list, search, read_note, create_note."

"""
Persona packs — shareable, diffable profiles that bundle playbooks, watchers,
and routing preferences.

Each persona is a JSON document that can be exported, shared, and imported.
Built from the existing personas directory + forge pipeline.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

from viki.config.logger import viki_logger


@dataclass
class PersonaPack:
    """A complete persona profile that can be exported and shared."""

    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    playbook_patterns: list[str] = field(default_factory=list)
    watcher_configs: list[dict[str, Any]] = field(default_factory=list)
    routing_preferences: dict[str, Any] = field(default_factory=dict)
    system_prompt: str = ""
    model_preferences: dict[str, str] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "playbook_patterns": self.playbook_patterns,
            "watcher_configs": self.watcher_configs,
            "routing_preferences": self.routing_preferences,
            "system_prompt": self.system_prompt,
            "model_preferences": self.model_preferences,
            "tags": self.tags,
            "created_at": self.created_at or time.time(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> PersonaPack:
        p = cls(
            name=data["name"],
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            author=data.get("author", ""),
            playbook_patterns=data.get("playbook_patterns", []),
            watcher_configs=data.get("watcher_configs", []),
            routing_preferences=data.get("routing_preferences", {}),
            system_prompt=data.get("system_prompt", ""),
            model_preferences=data.get("model_preferences", {}),
            tags=data.get("tags", []),
            created_at=data.get("created_at", 0),
        )
        return p


# Built-in persona templates
PERSONA_TEMPLATES: dict[str, PersonaPack] = {
    "engineer": PersonaPack(
        name="engineer",
        description="Software engineer persona with coding workflow, git context, and test integration",
        playbook_patterns=["python-patterns", "fastapi-patterns", "docker-patterns"],
        routing_preferences={"task_types": {"coding": 0.9, "research": 0.1}},
        system_prompt="You are an expert software engineer. Focus on clean code, tests, and best practices.",
        tags=["engineering", "development", "coding"],
    ),
    "researcher": PersonaPack(
        name="researcher",
        description="Research assistant persona with web research, PDF analysis, and knowledge synthesis",
        playbook_patterns=["research-patterns", "data-analysis-patterns"],
        routing_preferences={"task_types": {"research": 0.8, "writing": 0.2}},
        system_prompt="You are a thorough research assistant. Cite sources and synthesize findings.",
        tags=["research", "analysis", "writing"],
    ),
    "writer": PersonaPack(
        name="writer",
        description="Creative writer persona with style analysis, editing, and content generation",
        playbook_patterns=["writing-patterns", "content-patterns"],
        routing_preferences={"task_types": {"creative": 0.7, "research": 0.3}},
        system_prompt="You are a skilled writer. Adapt your style to the audience and purpose.",
        tags=["writing", "creative", "content"],
    ),
}


class PersonaManager:
    """
    Manages persona packs — export, import, list, and apply.

    Personas bundle playbook patterns, watcher configs, routing preferences,
    and model preferences into shareable, diffable profiles.
    """

    def __init__(self, data_dir: str = "./data/personas"):
        self._data_dir = data_dir
        self._personas_path = os.path.join(data_dir, "personas.json")
        self._personas: dict[str, PersonaPack] = {}
        self._active_persona: str = ""
        os.makedirs(data_dir, exist_ok=True)

        # Load built-in templates
        for name, template in PERSONA_TEMPLATES.items():
            self._personas[name] = template

        self._load()

    def list_personas(self) -> list[PersonaPack]:
        return list(self._personas.values())

    def get_persona(self, name: str) -> PersonaPack | None:
        return self._personas.get(name)

    def create_persona(self, pack: PersonaPack) -> str:
        """Create or update a persona pack."""
        self._personas[pack.name] = pack
        self._save()
        viki_logger.info("PersonaManager: created persona '%s'", pack.name)
        return pack.name

    def delete_persona(self, name: str) -> bool:
        if name in PERSONA_TEMPLATES:
            return False
        if name in self._personas:
            del self._personas[name]
            self._save()
            return True
        return False

    def set_active(self, name: str) -> bool:
        if name in self._personas:
            self._active_persona = name
            viki_logger.info("PersonaManager: activated persona '%s'", name)
            return True
        return False

    def get_active(self) -> PersonaPack | None:
        return self._personas.get(self._active_persona)

    def export_persona(self, name: str, output_path: str) -> str:
        """Export a persona pack to a JSON file."""
        pack = self._personas.get(name)
        if pack is None:
            return f"Persona '{name}' not found"
        try:
            with open(output_path, "w") as f:
                json.dump(pack.to_dict(), f, indent=2)
            return f"Exported persona '{name}' to {output_path}"
        except Exception as e:
            return f"Export failed: {e}"

    def import_persona(self, path: str) -> str:
        """Import a persona pack from a JSON file."""
        try:
            with open(path) as f:
                data = json.load(f)
            pack = PersonaPack.from_dict(data)
            self._personas[pack.name] = pack
            self._save()
            return f"Imported persona '{pack.name}' from {path}"
        except Exception as e:
            return f"Import failed: {e}"

    def diff_personas(self, name_a: str, name_b: str) -> str:
        """Show differences between two personas."""
        a = self._personas.get(name_a)
        b = self._personas.get(name_b)
        if not a or not b:
            return "One or both personas not found"

        lines: list[str] = [f"Diff: {name_a} vs {name_b}"]
        if a.system_prompt != b.system_prompt:
            lines.append("  system_prompt: DIFFERS")
        if a.playbook_patterns != b.playbook_patterns:
            lines.append(
                f"  playbook_patterns: {name_a}={a.playbook_patterns}, {name_b}={b.playbook_patterns}"
            )
        if a.routing_preferences != b.routing_preferences:
            lines.append("  routing_preferences: DIFFERS")
        if a.model_preferences != b.model_preferences:
            lines.append("  model_preferences: DIFFERS")
        if not lines[1:]:
            lines.append("  (identical)")
        return "\n".join(lines)

    def _save(self) -> None:
        try:
            data = {name: pack.to_dict() for name, pack in self._personas.items()}
            with open(self._personas_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            viki_logger.error("PersonaManager: save failed: %s", e)

    def _load(self) -> None:
        if not os.path.exists(self._personas_path):
            return
        try:
            with open(self._personas_path) as f:
                data = json.load(f)
            for name, pack_data in data.items():
                if name not in PERSONA_TEMPLATES:
                    self._personas[name] = PersonaPack.from_dict(pack_data)
        except Exception as e:
            viki_logger.error("PersonaManager: load failed: %s", e)

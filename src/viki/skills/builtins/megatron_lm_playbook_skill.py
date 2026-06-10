from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from config.logger import viki_logger
from skills.base import BaseSkill


class MegatronLmPlaybookSkill(BaseSkill):
    """Loads Cursor-style SKILL.md bundles vendored from NVIDIA Megatron-LM."""

    def __init__(self, controller: Optional[Any] = None) -> None:
        self._controller = controller
        self._skills_root = Path(__file__).resolve().parent.parent / "playbooks" / "megatron_lm"
        self._slug_to_path: Dict[str, Path] = self._discover_skills()
        self._cache: Dict[str, str] = {}

    @property
    def name(self) -> str:
        return "megatron_lm_playbook"

    @property
    def description(self) -> str:
        return (
            "Loads NVIDIA Megatron-LM repository agent skills (containers, uv, CI, Slurm, "
            "linting, testing, golden values, GitHub issues/PRs). For Megatron-LM / Megatron Core work."
        )

    @property
    def safety_tier(self) -> str:
        return "safe"

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "playbook": {
                    "type": "string",
                    "enum": sorted(self._slug_to_path.keys()),
                    "description": "Megatron-LM skill id (upstream skills/ folder name).",
                },
                "section": {
                    "type": "string",
                    "description": "Optional markdown heading to return.",
                },
                "format": {
                    "type": "string",
                    "enum": ["markdown", "summary"],
                    "default": "markdown",
                    "description": "Return full markdown or a compact summary.",
                },
            },
            "required": ["playbook"],
        }

    @property
    def triggers(self) -> List[str]:
        return [
            "megatron",
            "megatron-lm",
            "megatron core",
            "mcore",
            "tensor parallel",
            "pipeline parallel",
            "megatron bridge",
            "transformer engine",
            "uv.lock",
            "slurm",
            "pyxis",
            "enroot",
            "golden values",
            "megatron ci",
            "nvidia megatron",
        ]

    def _discover_skills(self) -> Dict[str, Path]:
        slug_to_path: Dict[str, Path] = {}
        if not self._skills_root.exists():
            viki_logger.warning("megatron_lm_playbook: skills root not found at %s", self._skills_root)
            return slug_to_path
        for path in sorted(self._skills_root.iterdir()):
            if not path.is_dir():
                continue
            if path.name.startswith(".") or path.name in ("__pycache__",):
                continue
            skill_md = path / "SKILL.md"
            if skill_md.is_file():
                slug_to_path[path.name] = skill_md
        return slug_to_path

    def _load_playbook(self, slug: str) -> Optional[str]:
        if slug in self._cache:
            return self._cache[slug]
        path = self._slug_to_path.get(slug)
        if not path:
            return None
        text = path.read_text(encoding="utf-8")
        self._cache[slug] = text
        return text

    @staticmethod
    def _extract_section(markdown: str, section_name: str) -> Optional[str]:
        lines = markdown.splitlines()
        target = section_name.strip().lower()
        start = None
        level = None
        heading_re = re.compile(r"^(#{1,6})\s+(.*)$")
        for idx, line in enumerate(lines):
            match = heading_re.match(line.strip())
            if not match:
                continue
            heading_level = len(match.group(1))
            heading_text = match.group(2).strip().lower()
            if start is None and (heading_text == target or target in heading_text):
                start = idx
                level = heading_level
                continue
            if start is not None and heading_level <= (level or 6):
                return "\n".join(lines[start:idx]).strip()
        if start is not None:
            return "\n".join(lines[start:]).strip()
        return None

    @staticmethod
    def _summary(markdown: str) -> str:
        lines = markdown.splitlines()
        h1 = next((line.strip() for line in lines if line.strip().startswith("# ")), "# Untitled")
        first_paragraph = ""
        headings: List[str] = []
        paragraph_lines: List[str] = []
        seen_h1 = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("# "):
                seen_h1 = True
                continue
            if not seen_h1:
                continue
            if stripped.startswith("## "):
                headings.append(stripped[3:].strip())
            if not first_paragraph:
                if stripped.startswith("#"):
                    continue
                if stripped:
                    paragraph_lines.append(stripped)
                elif paragraph_lines:
                    first_paragraph = " ".join(paragraph_lines).strip()
        if not first_paragraph and paragraph_lines:
            first_paragraph = " ".join(paragraph_lines).strip()
        heading_lines = "\n".join(f"- {heading}" for heading in headings) if headings else "- (none)"
        return f"{h1}\n\n{first_paragraph}\n\n## Headings\n{heading_lines}".strip()

    async def execute(self, params: Dict[str, Any]) -> str:
        pfx = "megatron_lm_playbook"
        slug = str(params.get("playbook") or "").strip()
        if not slug:
            return f"{pfx}: 'playbook' is required."

        markdown = self._load_playbook(slug)
        if markdown is None:
            valid = ", ".join(sorted(self._slug_to_path.keys()))
            return f"{pfx}: unknown playbook '{slug}'. Valid playbooks: {valid}"

        section = params.get("section")
        fmt = str(params.get("format") or "markdown").strip().lower()

        if section:
            section_text = str(section)
            extracted = self._extract_section(markdown, section_text)
            if extracted is None and section_text.strip().lower() == "process":
                for alias in ("workflow", "cycle", "checklist", "implementation rules"):
                    extracted = self._extract_section(markdown, alias)
                    if extracted is not None:
                        break
            if extracted is None:
                return f"{pfx}: section '{section}' not found in '{slug}'."
            markdown = extracted

        if fmt == "summary":
            return self._summary(markdown)
        if fmt != "markdown":
            return f"{pfx}: format must be 'markdown' or 'summary'."
        return markdown

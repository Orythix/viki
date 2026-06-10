from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from viki.config.logger import viki_logger
from viki.skills.base import BaseSkill


class EngineeringPlaybookSkill(BaseSkill):
    def __init__(self, controller: Optional[Any] = None) -> None:
        self._controller = controller
        self._playbooks_dir = Path(__file__).resolve().parent.parent / "playbooks"
        self._slug_to_path: Dict[str, Path] = self._discover_playbooks()
        self._cache: Dict[str, str] = {}

    @property
    def name(self) -> str:
        return "engineering_playbook"

    @property
    def description(self) -> str:
        return (
            "Loads structured engineering workflows (spec, plan, build, test, review, ship) "
            "sourced from addyosmani/agent-skills and returns the requested playbook."
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
                    "description": "Playbook slug to load.",
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
            "spec", "prd", "requirements", "acceptance criteria", "task breakdown",
            "plan", "implementation", "incremental", "tdd", "test-first", "build",
            "source of truth", "api design", "interface design", "frontend", "ui",
            "devtools", "browser testing", "debugging", "error recovery", "review",
            "code review", "quality", "simplify", "refactor", "security", "threat model",
            "hardening", "performance", "latency", "profiling", "git workflow",
            "versioning", "ci", "cd", "automation", "deprecation", "migration",
            "documentation", "adr", "launch", "rollout", "release",
        ]

    def _discover_playbooks(self) -> Dict[str, Path]:
        slug_to_path: Dict[str, Path] = {}
        if not self._playbooks_dir.exists():
            viki_logger.warning("engineering_playbook: playbooks dir not found at %s", self._playbooks_dir)
            return slug_to_path

        # 1. Original logic for legacy folders
        for folder in ("engineering", "references", "personas"):
            target = self._playbooks_dir / folder
            if not target.exists():
                continue
            for path in target.glob("*.md"):
                slug_to_path[path.stem] = path

        # 2. ECC playbooks (subdirectories containing SKILL.md or other .md)
        for target in self._playbooks_dir.iterdir():
            if target.is_dir() and target.name not in ("engineering", "references", "personas"):
                skill_file = target / "SKILL.md"
                if skill_file.exists():
                    slug_to_path[target.name] = skill_file
                else:
                    # Fallback to the first available .md file in the folder
                    md_files = list(target.glob("*.md"))
                    if md_files:
                        slug_to_path[target.name] = md_files[0]

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
        slug = str(params.get("playbook") or "").strip()
        if not slug:
            return "engineering_playbook: 'playbook' is required."

        markdown = self._load_playbook(slug)
        if markdown is None:
            valid = ", ".join(sorted(self._slug_to_path.keys()))
            return f"engineering_playbook: unknown playbook '{slug}'. Valid playbooks: {valid}"

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
                return f"engineering_playbook: section '{section}' not found in '{slug}'."
            markdown = extracted

        if fmt == "summary":
            return self._summary(markdown)
        if fmt != "markdown":
            return "engineering_playbook: format must be 'markdown' or 'summary'."
        return markdown

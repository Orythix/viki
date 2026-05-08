from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from viki.skills.base import BaseSkill

@dataclass
class Capability:
    name: str  # Unique identifier (e.g., 'internet_research')
    description: str
    safety_tier: str  # 'safe', 'medium', 'destructive'
    read_only: bool
    requires_confirmation: bool
    enabled: bool = True
    linked_skills: List[str] = field(default_factory=list) # Skills that implement this capability
    
    # Ratelimiting / Domain whitelisting metadata
    meta: Dict[str, any] = field(default_factory=dict)

@dataclass
class CapabilityCheckResult:
    allowed: bool
    exists: bool
    enabled: bool
    reason: str
    capability_name: Optional[str] = None

class CapabilityRegistry:
    def __init__(self):
        self.capabilities: Dict[str, Capability] = {}
        self._init_defaults()

    def _init_defaults(self):
        # Register standard capabilities
        self.register(Capability(
            name="internet_research",
            description="Access the public internet for search and reading content.",
            safety_tier="safe",
            read_only=True,
            requires_confirmation=False,
            linked_skills=["research"]
        ))
        self.register(Capability(
            name="filesystem_read",
            description="Read files and list directories on the local system.",
            safety_tier="safe",
            read_only=True,
            requires_confirmation=False,
            linked_skills=["filesystem", "filesystem_skill"]
        ))
        self.register(Capability(
            name="filesystem_write",
            description="Create, edit, or delete files on the local system.",
            safety_tier="medium",
            read_only=False,
            requires_confirmation=True,
            linked_skills=["filesystem", "filesystem_skill", "dev_tools"]
        ))
        self.register(Capability(
            name="shell_exec",
            description="Execute shell commands on the host OS.",
            safety_tier="destructive",
            read_only=False,
            requires_confirmation=True,
            linked_skills=["shell"]
        ))
        self.register(Capability(
            name="desktop_control",
            description="Manipulate windows and clipboard.",
            safety_tier="medium",
            read_only=False,
            requires_confirmation=False, # Medium but usually allowed
            linked_skills=["window_manager", "clipboard", "system_control"]
        ))
        # Phase 4: grounded computer-use loop is destructive (clicks, typing, drag).
        self.register(Capability(
            name="computer_use",
            description="Grounded UI vision + pyautogui actions (click, type, drag, navigate).",
            safety_tier="destructive",
            read_only=False,
            requires_confirmation=True,
            enabled=False,  # Off by default; user must explicitly enable.
            linked_skills=["computer_use"],
        ))
        self.register(Capability(
            name="email_calendar",
            description="Gmail and Google Calendar (read/send, list/add/remove events).",
            safety_tier="medium",
            read_only=False,
            requires_confirmation=False,
            linked_skills=["email", "calendar"]
        ))
        self.register(Capability(
            name="external_services",
            description="Twitter, image gen, messaging, summarize, Obsidian, tasks, Whisper, PDF, smart home, GIF.",
            safety_tier="medium",
            read_only=False,
            requires_confirmation=False,
            linked_skills=["twitter", "image_gen", "messaging", "summarize", "obsidian", "tasks", "whisper", "pdf", "smart_home", "gif"]
        ))
        self.register(Capability(
            name="content_creation",
            description="Data analysis, presentations (PPTX), spreadsheets, static websites.",
            safety_tier="medium",
            read_only=False,
            requires_confirmation=False,
            linked_skills=["data_analysis", "presentation", "spreadsheet", "website"]
        ))
        # Phase 3: Local code-aware skills (search index, planner/executor wrapper).
        self.register(Capability(
            name="code_intelligence",
            description="Repo-aware code search, planner/executor edits, and patch-and-verify (filesystem-write tier).",
            safety_tier="medium",
            read_only=False,
            requires_confirmation=False,
            linked_skills=["code_search", "plan_edit"],
        ))
        # Phase 0/3: low-risk utilities are default-allow so reflex/cortex can use them
        # without forcing the user to install an explicit capability.
        self.register(Capability(
            name="safe_utilities",
            description="Pure-compute or read-only utilities (math, time, thinking, recall, notifications, vision-passive).",
            safety_tier="safe",
            read_only=True,
            requires_confirmation=False,
            linked_skills=[
                "math_skill",
                "time_skill",
                "thinking_skill",
                "thinking",
                "recall",
                "notification",
                "vision",
                "internal_forge",
                "media_control",
                "browser",
                "voice",
                "swarm_council",
                "draw_overlay",
                "mount_focus",
                "security_tools",
                "short_video_agent",
                "sql_query",
                "aws_console",
                "kubernetes_ctl",
            ],
        ))

    def register(self, cap: Capability):
        self.capabilities[cap.name] = cap

    def get(self, name: str) -> Optional[Capability]:
        return self.capabilities.get(name)

    def _resolve_target_capability_name(
        self, skill_name: str, params: Dict[str, Any]
    ) -> Optional[str]:
        """Map a skill to its most appropriate capability name."""
        if skill_name == "research":
            return "internet_research"

        if skill_name in ["filesystem", "filesystem_skill"]:
            action = params.get("action")
            write_actions = {"write_file", "delete_file", "remove_file", "create_dir"}
            return "filesystem_write" if action in write_actions else "filesystem_read"

        fixed = {
            "shell": "shell_exec",
            "window_manager": "desktop_control",
            "clipboard": "desktop_control",
            "system_control": "desktop_control",
            "dev_tools": "filesystem_write",
            "email": "email_calendar",
            "calendar": "email_calendar",
        }
        if skill_name in fixed:
            return fixed[skill_name]

        external_services = {
            "twitter",
            "image_gen",
            "messaging",
            "summarize",
            "obsidian",
            "tasks",
            "whisper",
            "pdf",
            "smart_home",
            "gif",
        }
        if skill_name in external_services:
            return "external_services"

        content_creation = {"data_analysis", "presentation", "spreadsheet", "website"}
        if skill_name in content_creation:
            return "content_creation"

        return None

    def _capability_to_check_result(
        self, cap: Capability, target_cap_name: str
    ) -> CapabilityCheckResult:
        """Convert a capability object to a permission result."""
        if not cap.enabled:
            return CapabilityCheckResult(
                False,
                True,
                False,
                f"Capability '{target_cap_name}' is installed but currently DISABLED.",
                target_cap_name,
            )
        return CapabilityCheckResult(
            True,
            True,
            True,
            f"Permission granted by capability '{target_cap_name}'.",
            target_cap_name,
        )

    def check_permission(self, skill_name: str, params: Dict[str, Any] = None) -> CapabilityCheckResult:
        """
        Verify if a skill is allowed by any active capability.
        Returns a CapabilityCheckResult object.
        """
        params = params or {}
        
        # 1. Map skill to best-fit capability
        target_cap_name = self._resolve_target_capability_name(skill_name, params)

        # 2. Check the capability
        if target_cap_name:
            cap = self.get(target_cap_name)
            if not cap:
                return CapabilityCheckResult(
                    False,
                    False,
                    False,
                    f"Capability '{target_cap_name}' is NOT installed.",
                    target_cap_name,
                )
            return self._capability_to_check_result(cap, target_cap_name)

        # 3. Fallback: scan all linked skills
        for cap in self.capabilities.values():
            if skill_name in cap.linked_skills:
                if not cap.enabled:
                    return CapabilityCheckResult(False, True, False, f"Capability '{cap.name}' (linked to {skill_name}) is DISABLED.", cap.name)
                return CapabilityCheckResult(True, True, True, f"Permission granted by capability '{cap.name}'.", cap.name)
        
        return CapabilityCheckResult(False, False, False, f"No capability found in registry for skill '{skill_name}'.", None)

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
            linked_skills=["filesystem", "filesystem_skill"]
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

    def register(self, cap: Capability):
        self.capabilities[cap.name] = cap

    def get(self, name: str) -> Optional[Capability]:
        return self.capabilities.get(name)

    def check_permission(self, skill_name: str, params: Dict[str, Any] = None) -> CapabilityCheckResult:
        """
        Verify if a skill is allowed by any active capability.
        Returns a CapabilityCheckResult object.
        """
        params = params or {}
        
        # 1. Map skill to best-fit capability
        target_cap_name = None
        if skill_name == "research":
             target_cap_name = "internet_research"
        elif skill_name in ["filesystem", "filesystem_skill"]:
             action = params.get("action")
             if action in ["write_file", "delete_file", "remove_file", "create_dir"]:
                 target_cap_name = "filesystem_write"
             else:
                 target_cap_name = "filesystem_read"
        elif skill_name == "shell":
             target_cap_name = "shell_exec"
        elif skill_name in ["window_manager", "clipboard", "system_control"]:
             target_cap_name = "desktop_control"

        # 2. Check the capacity
        if target_cap_name:
             cap = self.get(target_cap_name)
             if not cap:
                 return CapabilityCheckResult(False, False, False, f"Capability '{target_cap_name}' is NOT installed.", target_cap_name)
             if not cap.enabled:
                 return CapabilityCheckResult(False, True, False, f"Capability '{target_cap_name}' is installed but currently DISABLED.", target_cap_name)
             return CapabilityCheckResult(True, True, True, f"Permission granted by capability '{target_cap_name}'.", target_cap_name)

        # 3. Fallback: scan all linked skills
        for cap in self.capabilities.values():
            if skill_name in cap.linked_skills:
                if not cap.enabled:
                    return CapabilityCheckResult(False, True, False, f"Capability '{cap.name}' (linked to {skill_name}) is DISABLED.", cap.name)
                return CapabilityCheckResult(True, True, True, f"Permission granted by capability '{cap.name}'.", cap.name)
        
        return CapabilityCheckResult(False, False, False, f"No capability found in registry for skill '{skill_name}'.", None)

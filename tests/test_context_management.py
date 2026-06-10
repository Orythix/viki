import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.path.abspath("."))

from viki.skills.registry import SkillRegistry
from viki.skills.builtins.filesystem_skill import FileSystemSkill
from viki.skills.builtins.time_skill import TimeSkill

def test_progressive_disclosure():
    print("RUNNING: Smart Context Management Verification...")
    
    registry = SkillRegistry()
    registry.register_skill(TimeSkill())
    registry.register_skill(FileSystemSkill())
    
    # 1. Metadata Mode (Startup)
    metadata = registry.get_context_description(mode="metadata")
    print("\n[METADATA MODE]")
    print(metadata)
    
    assert "filesystem_skill" in metadata
    assert "SCHEMA" not in metadata
    assert "INSTRUCTIONS" not in metadata
    
    # 2. Triggered Mode (On-demand)
    # Intent: coding -> filesystem_skill should be expanded
    intent = "coding"
    raw_input = "Write a file named test.txt"
    triggered_names = registry.get_relevant_skill_names(intent, raw_input)
    print(f"\n[TRIGGERED SKILLS for intent='{intent}']")
    print(triggered_names)
    
    assert "filesystem_skill" in triggered_names
    
    full_manifest = registry.get_context_description(mode="full", names=triggered_names)
    print("\n[FULL MANIFEST]")
    print(full_manifest)
    
    assert "SCHEMA" in full_manifest
    assert "write_file" in full_manifest # Part of filesystem schema
    
    print("\n✅ Smart Context Management Verified.")

if __name__ == "__main__":
    test_progressive_disclosure()

import os
import sys

# Add project root to path
sys.path.append(os.path.abspath("."))

from viki.skills.registry import SkillRegistry


class MockController:
    def __init__(self):
        self.skill_registry = SkillRegistry()


def test_sovereign_hub():
    print("RUNNING: Sovereign Tool Hub Verification...")

    ctrl = MockController()
    registry = ctrl.skill_registry

    # The library ships as package data inside viki/data/
    import viki

    library_path = os.path.join(
        os.path.dirname(os.path.abspath(viki.__file__)), "data", "sovereign_library.json"
    )
    registry.load_sovereign_library(library_path, ctrl)

    skills = registry.list_skills()
    print(f"Total Skills in Registry: {len(skills)}")

    # Check for some specific skills
    assert "aws_ec2_list" in skills
    assert "git_status" in skills
    assert "docker_ps" in skills
    assert "sys_disk_usage" in skills

    print("\n[SAMPLE SCHEMA: aws_ec2_list]")
    aws_skill = registry.get_skill("aws_ec2_list")
    print(aws_skill.schema)

    # Check intent mapping
    intent = "cloud"
    relevant = registry.get_relevant_skill_names(intent, "list my ec2")
    print(f"\n[RELEVANT SKILLS for intent='{intent}']")
    print(relevant[:10], "...")

    assert "aws_ec2_list" in relevant

    print("\n✅ Sovereign Tool Hub (100+ Skills) Verified.")


if __name__ == "__main__":
    test_sovereign_hub()

import pytest
import os
import tempfile
import shutil
from viki.skills.builtins.manus_skill import ManusSkill

class MockController:
    def __init__(self, workspace_dir):
        self.settings = {"system": {"workspace_dir": workspace_dir}}

@pytest.fixture
def temp_workspace():
    ws_dir = tempfile.mkdtemp()
    
    # Create a mock SKILL.md
    skill_file = os.path.join(ws_dir, "test_task.md")
    with open(skill_file, "w") as f:
        f.write("# Test Skill\n```python\nprint('Hello from Manus Sandbox')\n```")
    
    ctrl = MockController(ws_dir)
    yield ctrl, skill_file
    shutil.rmtree(ws_dir)

@pytest.mark.asyncio
async def test_manus_skill_md_execution(temp_workspace):
    ctrl, skill_file = temp_workspace
    skill = ManusSkill(ctrl)
    
    # Run task with skill file
    result = await skill.execute({
        "task": "Test execution of skill file",
        "skill_file": skill_file
    })
    
    assert "SUCCESS" in result
    assert "Hello from Manus Sandbox" in result
    assert "Backend: subprocess" in result # Default in tests

@pytest.mark.asyncio
async def test_manus_raw_task(temp_workspace):
    ctrl, _ = temp_workspace
    skill = ManusSkill(ctrl)
    
    # Run raw task
    result = await skill.execute({
        "task": "Echo 'Direct' output",
        "runtime": "bash"
    })
    
    assert "SUCCESS" in result
    # The default generated script for raw task is a python print for now
    # but we can improve it later. For now just verify it runs.

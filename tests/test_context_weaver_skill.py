import pytest
import os
import tempfile
import shutil
from viki.skills.builtins.context_weaver_skill import ContextWeaverSkill
from viki.core.utils.context_retriever import ContextRetriever

class MockController:
    def __init__(self, workspace_dir):
        self.context_retriever = ContextRetriever(workspace_dir)

@pytest.fixture
def temp_workspace():
    ws_dir = tempfile.mkdtemp()
    # Create a test file
    test_file = os.path.join(ws_dir, "important.py")
    with open(test_file, "w") as f:
        f.write("print('essential logic')")
    
    ctrl = MockController(ws_dir)
    yield ctrl, test_file
    shutil.rmtree(ws_dir)

@pytest.mark.asyncio
async def test_weaver_pin(temp_workspace):
    ctrl, test_file = temp_workspace
    skill = ContextWeaverSkill(ctrl)
    
    # Pin the file
    result = await skill.execute({"action": "pin", "path": test_file})
    assert "Successfully pinned" in result
    assert test_file in ctrl.context_retriever.pinned_paths

@pytest.mark.asyncio
async def test_weaver_list(temp_workspace):
    ctrl, test_file = temp_workspace
    skill = ContextWeaverSkill(ctrl)
    await skill.execute({"action": "pin", "path": test_file})
    
    result = await skill.execute({"action": "list"})
    assert "important.py" in result

@pytest.mark.asyncio
async def test_weaver_unpin(temp_workspace):
    ctrl, test_file = temp_workspace
    skill = ContextWeaverSkill(ctrl)
    await skill.execute({"action": "pin", "path": test_file})
    
    # Unpin
    result = await skill.execute({"action": "unpin", "path": test_file})
    assert "Unpinned" in result
    assert len(ctrl.context_retriever.pinned_paths) == 0

@pytest.mark.asyncio
async def test_weaver_retrieval_integration(temp_workspace):
    ctrl, test_file = temp_workspace
    skill = ContextWeaverSkill(ctrl)
    await skill.execute({"action": "pin", "path": test_file})
    
    # Test retrieval
    context = await ctrl.context_retriever.get_relevant_context("query that doesn't match")
    assert "PINNED FILE: important.py" in context
    assert "essential logic" in context

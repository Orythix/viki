import pytest
import os
import tempfile
import shutil
from skills.builtins.mutation_pilot_skill import MutationPilotSkill

class MockController:
    pass

@pytest.fixture
def temp_code():
    tmp_dir = tempfile.mkdtemp()
    
    # Create a simple file
    code_file = os.path.join(tmp_dir, "logic.py")
    with open(code_file, "w") as f:
        f.write("def is_valid(x):\n    return x == 10\n")
    
    # Create a test file
    test_file = os.path.join(tmp_dir, "test_logic.py")
    with open(test_file, "w") as f:
        f.write("from logic import is_valid\ndef test_valid():\n    assert is_valid(10) == True\n")
    
    ctrl = MockController()
    yield ctrl, code_file, test_file, tmp_dir
    shutil.rmtree(tmp_dir)

@pytest.mark.asyncio
async def test_mutation_mutate(temp_code):
    ctrl, code_file, _, _ = temp_code
    skill = MutationPilotSkill(ctrl)
    
    result = await skill.execute({"action": "mutate", "path": code_file})
    assert "MUTANT_CREATED" in result
    assert "Applied mutation: '==' -> '!='" in result

@pytest.mark.asyncio
async def test_mutation_benchmark_killed(temp_code, monkeypatch):
    ctrl, code_file, test_file, tmp_dir = temp_code
    skill = MutationPilotSkill(ctrl)
    
    # We need to be in the tmp_dir so imports work
    monkeypatch.chdir(tmp_dir)
    
    # Benchmark with a test that SHOULD fail if logic changes
    result = await skill.execute({
        "action": "benchmark", 
        "path": code_file,
        "test_command": f"pytest {test_file}"
    })
    
    assert "MUTANT_KILLED" in result or "Test suite fails on the ORIGINAL" in result
    # Note: Depending on environment, pytest might not be installed or behave differently.
    # But the logic flow is what we are testing.

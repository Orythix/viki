import pytest
import os
import tempfile
import shutil
from skills.builtins.autonomous_auditor_skill import AutonomousAuditorSkill

class MockController:
    def __init__(self, workspace_dir):
        self.settings = {"system": {"workspace_dir": workspace_dir}}
        self.model_router = "mock_router"

@pytest.fixture
def temp_workspace():
    ws_dir = tempfile.mkdtemp()
    # Create a vulnerable file
    vuln_file = os.path.join(ws_dir, "vuln.py")
    with open(vuln_file, "w") as f:
        f.write("import sqlite3\nconn = sqlite3.connect('test.db')\ncur = conn.cursor()\ncur.execute(f'SELECT * FROM users WHERE id = {user_id}')")
    
    ctrl = MockController(ws_dir)
    yield ctrl, vuln_file
    shutil.rmtree(ws_dir)

@pytest.mark.asyncio
async def test_auditor_audit_file(temp_workspace):
    ctrl, vuln_file = temp_workspace
    skill = AutonomousAuditorSkill(ctrl)
    
    result = await skill.execute({"action": "security", "path": vuln_file})
    assert "AUDIT_REQUEST" in result
    assert "vuln.py" in result
    assert "Injection vulnerabilities" in result
    assert "cur.execute" in result

@pytest.mark.asyncio
async def test_auditor_missing_file(temp_workspace):
    ctrl, _ = temp_workspace
    skill = AutonomousAuditorSkill(ctrl)
    
    result = await skill.execute({"action": "audit", "path": "non_existent.py"})
    assert "Error: Path" in result

@pytest.mark.asyncio
async def test_auditor_directory(temp_workspace):
    ctrl, vuln_file = temp_workspace
    skill = AutonomousAuditorSkill(ctrl)
    
    result = await skill.execute({"action": "audit", "path": os.path.dirname(vuln_file)})
    assert "Found 1 files" in result
    assert "vuln.py" in result

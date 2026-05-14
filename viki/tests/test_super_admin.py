import pytest
import os
import shutil
import asyncio
import yaml
from viki.core.super_admin import SuperAdminLayer
from viki.core.orchestrator import VIKIController

@pytest.fixture
async def admin_setup():
    # Setup test paths
    test_data_dir = os.path.abspath("./tests/data_admin")
    if os.path.exists(test_data_dir):
        shutil.rmtree(test_data_dir)
    os.makedirs(test_data_dir)

    # Resolve config paths
    base_dir = os.path.dirname(os.path.abspath(__file__))
    viki_dir = os.path.dirname(base_dir)
    
    models_config = os.path.join(base_dir, "test_models.yaml")
    soul_path = os.path.join(viki_dir, "config", "soul.yaml")

    # Snapshot environment
    old_secret = os.environ.get("VIKI_ADMIN_SECRET")
    os.environ["VIKI_ADMIN_SECRET"] = "TEST_SECRET"

    # Test Admin Config
    admin_config_path = os.path.abspath("./tests/test_admin.yaml")
    with open(admin_config_path, 'w') as f:
        f.write("admin_id: TEST_ID\nadmin_secret: TEST_SECRET\nlogs_path: ./tests/data_admin/logs.txt")
        
    settings = {
        "system": {
            "data_dir": test_data_dir,
            "workspace_dir": os.path.abspath("./workspace")
        },
        "models_config": models_config
    }
    settings_path = os.path.abspath("./tests/temp_settings_admin.yaml")
    with open(settings_path, 'w') as f:
        yaml.dump(settings, f)
        
    # Init Controller
    controller = VIKIController(settings_path, soul_path)
    controller.super_admin = SuperAdminLayer(admin_config_path)
    
    yield controller, test_data_dir

    # Cleanup
    await controller.shutdown()
    
    if old_secret is None:
        os.environ.pop("VIKI_ADMIN_SECRET", None)
    else:
        os.environ["VIKI_ADMIN_SECRET"] = old_secret

    for path in [test_data_dir, admin_config_path, settings_path]:
        if os.path.exists(path):
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
            except:
                pass

@pytest.mark.asyncio
async def test_admin_kill_switch(admin_setup):
    controller, test_data_dir = admin_setup
    
    # 1. Normal Request
    resp = await controller.process_request("Hello")
    assert "HALTED" not in resp
    
    # 2. Invalid Admin Command (Wrong Secret)
    resp = await controller.process_request("ADMIN TEST_ID WRONG_SECRET KILL")
    assert "HALTED" not in resp
    
    # 3. Valid Kill Switch
    resp = await controller.process_request("ADMIN TEST_ID TEST_SECRET KILL")
    assert "HALTED" in resp
    
    # 4. Verify system logs created
    log_path = os.path.join(test_data_dir, "logs.txt")
    assert os.path.exists(log_path)
    
    # 5. Verify subsequent requests fail
    resp = await controller.process_request("Are you there?")
    assert "HALTED" in resp

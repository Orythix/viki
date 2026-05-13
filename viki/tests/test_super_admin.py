import unittest
import os
import sys
import shutil
import asyncio

# Add project root (parent of viki folder) to path
sys.path.append(os.path.abspath(os.path.join(os.getcwd(), '..')))

from viki.core.super_admin import SuperAdminLayer
from viki.core.orchestrator import VIKIController

class TestSuperAdmin(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Setup test paths
        self.test_data_dir = os.path.abspath("./tests/data_admin")
        if os.path.exists(self.test_data_dir):
            shutil.rmtree(self.test_data_dir)
        os.makedirs(self.test_data_dir)

        # Resolve config paths relative to project root
        base_dir = os.path.dirname(os.path.abspath(__file__))
        viki_dir = os.path.dirname(base_dir)
        
        models_config = os.path.join(base_dir, "test_models.yaml")
        self.soul_path = os.path.join(viki_dir, "config", "soul.yaml")

        # Force the SuperAdminLayer to read TEST_SECRET
        self._env_snapshot = {
            "VIKI_ADMIN_SECRET": os.environ.get("VIKI_ADMIN_SECRET"),
        }
        os.environ["VIKI_ADMIN_SECRET"] = "TEST_SECRET"

        # Test Admin Config
        self.admin_config_path = os.path.abspath("./tests/test_admin.yaml")
        with open(self.admin_config_path, 'w') as f:
            f.write("admin_id: TEST_ID\nadmin_secret: TEST_SECRET\nlogs_path: ./tests/data_admin/logs.txt")
            
        self.settings = {
            "system": {
                "data_dir": self.test_data_dir,
                "workspace_dir": os.path.abspath("./workspace")
            },
            "models_config": models_config
        }
        self.settings_path = os.path.abspath("./tests/temp_settings_admin.yaml")
        import yaml
        with open(self.settings_path, 'w') as f:
            yaml.dump(self.settings, f)
            
        # Init Controller
        self.controller = VIKIController(self.settings_path, self.soul_path)
        self.controller.super_admin = SuperAdminLayer(self.admin_config_path)
            
    async def asyncTearDown(self):
        if hasattr(self, 'controller') and self.controller:
            try:
                await asyncio.wait_for(self.controller.shutdown(), timeout=10.0)
            except Exception:
                if hasattr(self.controller, "close"):
                    self.controller.close()

        for k, v in getattr(self, "_env_snapshot", {}).items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

        if os.path.exists(self.test_data_dir):
            try:
                shutil.rmtree(self.test_data_dir)
            except:
                pass
        if os.path.exists(self.admin_config_path):
            try:
                os.remove(self.admin_config_path)
            except:
                pass
        if os.path.exists(self.settings_path):
            try:
                os.remove(self.settings_path)
            except:
                pass

    async def test_admin_kill_switch(self):
        # 1. Normal Request
        resp = await self.controller.process_request("Hello")
        self.assertNotIn("HALTED", resp)
        
        # 2. Invalid Admin Command (Wrong Secret)
        resp = await self.controller.process_request("ADMIN TEST_ID WRONG_SECRET KILL")
        self.assertNotIn("HALTED", resp)
        
        # 3. Valid Kill Switch
        resp = await self.controller.process_request("ADMIN TEST_ID TEST_SECRET KILL")
        self.assertIn("HALTED", resp)
        
        # 4. Verify system logs created
        log_path = os.path.join(self.test_data_dir, "logs.txt")
        self.assertTrue(os.path.exists(log_path))
        
        # 5. Verify subsequent requests fail
        resp = await self.controller.process_request("Are you there?")
        self.assertIn("HALTED", resp)

if __name__ == '__main__':
    unittest.main()

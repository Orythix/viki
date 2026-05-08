import unittest
import os
import sys
import shutil

# Add project root (parent of viki folder) to path
sys.path.append(os.path.abspath(os.path.join(os.getcwd(), '..')))

from viki.core.super_admin import SuperAdminLayer
from viki.core.controller import VIKIController

class TestSuperAdmin(unittest.TestCase):
    def setUp(self):
        # Setup test paths
        self.test_data_dir = "./tests/data_admin"
        if os.path.exists(self.test_data_dir):
            shutil.rmtree(self.test_data_dir)
        os.makedirs(self.test_data_dir)

        # Force the SuperAdminLayer to read TEST_SECRET, not whatever lives in
        # the developer's local .env (which other tests may have loaded via
        # `load_dotenv()` when importing `viki.api.server`). Snapshot the env
        # so we restore it in tearDown and don't leak into other tests.
        self._env_snapshot = {
            "VIKI_ADMIN_SECRET": os.environ.get("VIKI_ADMIN_SECRET"),
        }
        os.environ["VIKI_ADMIN_SECRET"] = "TEST_SECRET"

        # Test Admin Config
        self.admin_config_path = "./tests/test_admin.yaml"
        with open(self.admin_config_path, 'w') as f:
            f.write("admin_id: TEST_ID\nadmin_secret: TEST_SECRET\nlogs_path: ./tests/data_admin/logs.txt")
            
        self.settings = {
            "system": {"data_dir": self.test_data_dir},
            "models_config": "./tests/test_models.yaml"
        }
        self.settings_path = "./tests/temp_settings_admin.yaml"
        import yaml
        with open(self.settings_path, 'w') as f:
            yaml.dump(self.settings, f)
            
        self.soul_path = "./config/soul.yaml"
        
        # Init Controller but override admin layer manually for testing
        self.controller = VIKIController(self.settings_path, self.soul_path)
        self.controller.super_admin = SuperAdminLayer(self.admin_config_path)
            
    def tearDown(self):
        if hasattr(self, 'controller') and self.controller:
            import asyncio
            try:
                # Use a small wait for background tasks
                asyncio.run(asyncio.wait_for(self.controller.shutdown(), timeout=5.0))
            except:
                pass

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

    def async_test(coro):
        def wrapper(*args, **kwargs):
            import asyncio
            return asyncio.run(coro(*args, **kwargs))
        return wrapper

    @async_test
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
        log_path = "./tests/data_admin/logs.txt"
        self.assertTrue(os.path.exists(log_path))
        
        # 5. Verify subsequent requests fail (System is dead state)
        # Note: In real app this would be dead process. 
        # In this mock class, the 'shutdown_triggered' flag persists.
        resp = await self.controller.process_request("Are you there?")
        self.assertIn("HALTED", resp)

if __name__ == '__main__':
    unittest.main()

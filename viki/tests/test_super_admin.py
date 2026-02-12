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
        if os.path.exists(self.test_data_dir):
            try:
                shutil.rmtree(self.test_data_dir)
            except:
                pass
        if os.path.exists(self.admin_config_path):
            os.remove(self.admin_config_path)
        if os.path.exists(self.settings_path):
            try:
                os.remove(self.settings_path)
            except:
                pass

    def test_admin_kill_switch(self):
        # 1. Normal Request
        resp = self.controller.process_request("Hello")
        self.assertNotIn("HALTED", resp)
        
        # 2. Invalid Admin Command (Wrong Secret)
        resp = self.controller.process_request("ADMIN TEST_ID WRONG_SECRET KILL")
        self.assertNotIn("HALTED", resp)
        
        # 3. Valid Kill Switch
        resp = self.controller.process_request("ADMIN TEST_ID TEST_SECRET KILL")
        self.assertIn("HALTED", resp)
        
        # 4. Verify system logs created
        log_path = "./tests/data_admin/logs.txt"
        self.assertTrue(os.path.exists(log_path))
        
        # 5. Verify subsequent requests fail (System is dead state)
        # Note: In real app this would be dead process. 
        # In this mock class, the 'shutdown_triggered' flag persists.
        resp = self.controller.process_request("Are you there?")
        self.assertIn("HALTED", resp)

if __name__ == '__main__':
    unittest.main()

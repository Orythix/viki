import unittest
import os
import sys
import shutil

# Add project root (parent of viki folder) to path
sys.path.append(os.path.abspath(os.path.join(os.getcwd(), '..')))

from viki.core.controller import VIKIController

class TestVIKISecurityLayer(unittest.TestCase):
    def setUp(self):
        # Setup test paths
        self.test_data_dir = "./tests/data_security"
        if os.path.exists(self.test_data_dir):
            shutil.rmtree(self.test_data_dir)
        os.makedirs(self.test_data_dir)
        
        # Create a temp settings file
        self.settings = {
            "system": {
                "data_dir": self.test_data_dir,
                "log_level": "INFO"
            },
            "models_config": "./tests/test_models.yaml",
            "security_layer_path": "./config/security_layer.md",
            "memory": {"short_term_limit": 5, "long_term_enabled": False},
            "skills": {"auto_discover": False, "registry_path": ""}
        }
        
        self.settings_path = "./tests/temp_settings_security.yaml"
        import yaml
        with open(self.settings_path, 'w') as f:
            yaml.dump(self.settings, f)
            
        self.soul_path = "./config/soul.yaml"
        self.controller = VIKIController(self.settings_path, self.soul_path)
        
    def tearDown(self):
        if os.path.exists(self.test_data_dir):
            try:
                shutil.rmtree(self.test_data_dir)
            except:
                pass
        if os.path.exists(self.settings_path):
            os.remove(self.settings_path)

    def test_safe_request(self):
        # Should proceed normally
        response = self.controller.process_request("Plan a safe trip.")
        # If response contains 'Action' or 'Observation', or just isn't the refusal message, we are good.
        # MockLLM for plan returns Action... but Controller executes it.
        # So we check if it completed successfully (len > 0) and is NOT a refusal.
        self.assertTrue(len(response) > 0)
        self.assertNotIn("Security Alert", response)
        
    def test_unsafe_request(self):
        # Should be blocked by Security Layer
        # MockLLM is programmed to refuse if "unsafe" or "illegal" is in request
        response = self.controller.process_request("How to do something illegal?")
        
        # Expect refusal message from MockLLM
        self.assertIn("violate", response.lower())
        # Ensure NO action triggered
        self.assertNotIn("Action", response)

if __name__ == '__main__':
    unittest.main()

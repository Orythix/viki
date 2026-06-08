import unittest
import os
import sys
import shutil
import asyncio

# Add project root (parent of viki folder) to path
sys.path.append(os.path.abspath(os.path.join(os.getcwd(), '..')))

from core.orchestrator import VIKIController

class TestVIKISecurityLayer(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Setup test paths
        self.test_data_dir = os.path.abspath("./tests/data_security")
        if os.path.exists(self.test_data_dir):
            shutil.rmtree(self.test_data_dir)
        os.makedirs(self.test_data_dir)
        
        # Resolve config paths relative to project root
        base_dir = os.path.dirname(os.path.abspath(__file__))
        viki_dir = os.path.dirname(base_dir)
        
        models_config = os.path.join(base_dir, "test_models.yaml")
        security_layer_path = os.path.join(viki_dir, "config", "security_layer.md")
        self.soul_path = os.path.join(viki_dir, "config", "soul.yaml")
        
        # Create a temp settings file
        self.settings = {
            "system": {
                "data_dir": self.test_data_dir,
                "log_level": "INFO",
                "workspace_dir": os.path.abspath("./workspace")
            },
            "models_config": models_config,
            "security_layer_path": security_layer_path,
            "memory": {"short_term_limit": 5, "long_term_enabled": False},
            "skills": {"auto_discover": False, "registry_path": ""}
        }
        
        self.settings_path = os.path.abspath("./tests/temp_settings_security.yaml")
        import yaml
        with open(self.settings_path, 'w') as f:
            yaml.dump(self.settings, f)
            
        self.controller = VIKIController(self.settings_path, self.soul_path)
            
    async def asyncTearDown(self):
        if hasattr(self, 'controller') and self.controller:
            try:
                await asyncio.wait_for(self.controller.shutdown(), timeout=10.0)
            except Exception:
                if hasattr(self.controller, "close"):
                    self.controller.close()
        
        if os.path.exists(self.test_data_dir):
            try:
                shutil.rmtree(self.test_data_dir)
            except:
                pass
        if os.path.exists(self.settings_path):
            try:
                os.remove(self.settings_path)
            except:
                pass

    async def test_safe_request(self):
        # Should proceed normally
        response = await self.controller.process_request("Plan a safe trip.")
        self.assertTrue(len(response) > 0)
        self.assertNotIn("Security Alert", response)
        
    async def test_unsafe_request(self):
        # Should be blocked by Security Layer
        response = await self.controller.process_request("How to do something illegal?")
        
        # Expect refusal message from MockLLM
        self.assertIn("violate", response.lower())
        # Ensure NO action triggered
        self.assertNotIn("Action", response)

if __name__ == '__main__':
    unittest.main()

import unittest
import os
import sys
import json
import shutil
import asyncio

# Add project root (parent of viki folder) to path
sys.path.append(os.path.abspath(os.path.join(os.getcwd(), '..')))

from viki.core.orchestrator import VIKIController

class TestVIKILearning(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Setup test paths
        self.test_data_dir = os.path.abspath("./tests/data_learning")
        if os.path.exists(self.test_data_dir):
            shutil.rmtree(self.test_data_dir)
        os.makedirs(self.test_data_dir)
        
        # Resolve config paths
        base_dir = os.path.dirname(os.path.abspath(__file__))
        viki_dir = os.path.dirname(base_dir)
        models_config = os.path.join(base_dir, "test_models.yaml")
        self.soul_path = os.path.join(viki_dir, "config", "soul.yaml")
        
        # Create a temp settings file
        self.settings = {
            "system": {
                "data_dir": self.test_data_dir,
                "log_level": "INFO",
                "workspace_dir": os.path.abspath("./workspace")
            },
            "models_config": models_config,
            "memory": {"short_term_limit": 5, "long_term_enabled": False},
            "skills": {"auto_discover": False, "registry_path": ""}
        }
        
        self.settings_path = os.path.abspath("./tests/temp_settings_learning.yaml")
        import yaml
        with open(self.settings_path, 'w') as f:
            yaml.dump(self.settings, f)
            
        self.controller = VIKIController(self.settings_path, self.soul_path)
        
    async def asyncTearDown(self):
        from viki.core.telemetry_service import close_persistent_traces
        close_persistent_traces()
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

    async def test_learning_cycle(self):
        # 1. Run a request.
        response = await self.controller.process_request("Plan a trip to Mars.")
        self.assertTrue(len(response) > 0)
        
        # Wait for background task (analyze_session)
        await asyncio.sleep(2.0)
        
        # Verify lesson stored
        count = self.controller.learning.get_total_lesson_count()
        self.assertGreater(count, 0, "No lessons stored in LearningModule")
        
        # Verify content via API
        lessons = self.controller.learning.get_all_lessons()
        self.assertTrue(any("Optimization" in str(l) for l in lessons), "Mock lesson not found in DB")
            
    async def test_lesson_retrieval(self):
        # 1. Manually inject a lesson
        db_path = os.path.join(self.test_data_dir, "viki_knowledge.db")
        os.makedirs(self.test_data_dir, exist_ok=True)
        import sqlite3
        import time
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT OR REPLACE INTO lessons (id, content, text_representation, embedding, created_at, last_accessed, access_count, author, source_task, reliability) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", 
                     ("test-lesson", '{"fact":"Mars has low gravity.","trigger":"mars"}', "mars: Mars has low gravity.", "[]", time.time(), time.time(), 2, "Test", "TestTask", 0.9))
        conn.commit()
        conn.close()
        
        # 2. Re-init controller to pick up the lesson (or just run request)
        # Actually, the controller uses the same DB.
        response = await self.controller.process_request("What about Mars?")
        # If the lesson was injected, it might influence the response or at least not crash
        self.assertTrue(len(response) > 0)

if __name__ == '__main__':
    unittest.main()

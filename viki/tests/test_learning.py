import unittest
import os
import sys
import json
import shutil

# Add project root (parent of viki folder) to path
sys.path.append(os.path.abspath(os.path.join(os.getcwd(), '..')))

from viki.core.controller import VIKIController

class TestVIKILearning(unittest.TestCase):
    def setUp(self):
        # Setup test paths
        self.test_data_dir = "./tests/data"
        if os.path.exists(self.test_data_dir):
            shutil.rmtree(self.test_data_dir)
        os.makedirs(self.test_data_dir)
        
        # Create a temp settings file using this data dir
        self.settings = {
            "system": {
                "data_dir": self.test_data_dir,
                "log_level": "INFO"
            },
            "models_config": "./tests/test_models.yaml",
            "memory": {"short_term_limit": 5, "long_term_enabled": False},
            "skills": {"auto_discover": False, "registry_path": ""}
        }
        
        self.settings_path = "./tests/temp_settings_learning.yaml"
        import yaml
        with open(self.settings_path, 'w') as f:
            yaml.dump(self.settings, f)
            
        self.soul_path = "./viki/config/soul.yaml"
        self.controller = VIKIController(self.settings_path, self.soul_path)
        
    def tearDown(self):
        if os.path.exists(self.test_data_dir):
            try:
                shutil.rmtree(self.test_data_dir)
            except:
                pass
        if os.path.exists(self.settings_path):
            os.remove(self.settings_path)

    def test_learning_cycle(self):
        # 1. Run a request. The MockLLM will:
        #    - Generate a regular detailed trace (Thinking/Action).
        #    - Then controller calls learning.analyze_session
        #    - MockLLM sees "optimization sub-routine" and returns a lesson JSON.
        #    - Controller stores lesson in lessons.json.
        
        response = self.controller.process_request("Plan a trip to Mars.")
        
        # Verify response happened (it completes successfully)
        # The final response is usually "Observation processed..." or similar
        self.assertTrue(len(response) > 0)
        
        # Wait for background thread
        import time
        time.sleep(0.5)
        
        # Verify lessons.json created
        lessons_path = os.path.join(self.test_data_dir, "lessons.json")
        self.assertTrue(os.path.exists(lessons_path), f"lessons.json not created in {self.test_data_dir}")
        
        with open(lessons_path, 'r') as f:
            lessons = json.load(f)
            self.assertTrue(len(lessons) > 0, "No lessons stored")
            self.assertEqual(lessons[0]['topic'], "planning")
            
        # 2. Run a second request to verified Context Injection
        # The MockLLM checks for "APPLY LEARNED HEURISTICS" and returns a special message if found.
        # Since retrieve_relevant_lessons uses naive retrieval (returns all for now), it should inject it.
        
        response_2 = self.controller.process_request("Another plan.")
        
        # Check if the MockLLM acknowledged the heuristics
        # Note: MockLLM returns "I see the heuristics..." if triggered.
        # But controller loop parses Actions.
        # "Action: thinking_skill.execute(topic='Heuristics Applied'...)"
        
        # The Action will be executed, result put in memory.
        # Then next turn MockLLM sees Function result.
        # It says "Observation processed..."
        # Finally returns.
        
        # We can check if "Heuristics Applied" is in the internal memory or final output if it propagated.
        # Or checking `response_2` might be tricky if it just returns final answer.
        
        # Actually, let's inspect the mock's output in the controller's memory if possible, 
        # or rely on the final output string if the mock flow allows.
        
        # If Mock outputs "Action: ...", Controller executes it.
        # ThinkingSkill executes -> "[INTERNAL THOUGHT] Planning for 'Heuristics Applied': ..."
        
        # The final output is usually sanitized last response.
        # If Mock finishes with "Observation processed", that might be the output.
        
        # Let's check if the lesson text is in the log or memory? 
        # Easier: Just check if we hit the "I see heuristics" path by ensuring response_2 is not just default.
        # Default for "plan" is "Action: thinking_skill(Simulating optimal path...)"
        
        # If heuristics injected, Mock returns "Action: thinking_skill... topic='Heuristics Applied'" instead.
        # So we check if "Heuristics Applied" appears in the execution trace or result.
        
        # But `process_request` returns `final_output` which is usually the last Assistant message.
        # If Mock loop runs:
        # Turn 1: Mock -> Action: thinking... (Heuristics Applied)
        # Turn 2: Skill -> Result ...
        # Turn 3: Mock -> Observation processed. Result: ...
        
        # Output will be "Observation processed..."
        # If default:
        # Turn 1: Mock -> Action: thinking... (Simulating optimal path...)
        # ...
        
        # So verifying the output content differs is enough.
        # But Mock for "plan" always returns ... wait.
        # `if "plan" in msg: return ...` is checked first in MockLLM line 64.
        # `if "APPLY LEARNED HEURISTICS"` is checked BEFORE that in line 74 (added).
        # So it should override "plan".
        
        self.assertIn("Heuristics Applied", response_2)

if __name__ == '__main__':
    unittest.main()

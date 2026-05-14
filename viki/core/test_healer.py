import os
import asyncio
import time
from typing import Dict, Any, Optional, List
from viki.config.logger import viki_logger

class TestHealerPipeline:
    """
    Autonomous pipeline that watches a test suite and attempts 
    self-healing if failures occur.
    """
    
    def __init__(self, controller):
        self.controller = controller
        self.active = False
        self.watch_path = None
        self.test_command = None
        self.interval = 300 # 5 minutes
        self._task = None

    def start(self, watch_path: str, test_command: str, interval: int = 300):
        """Start the autonomous healing loop."""
        self.watch_path = watch_path
        self.test_command = test_command
        self.interval = interval
        self.active = True
        
        if self._task:
            self._task.cancel()
            
        self._task = asyncio.create_task(self._run_loop())
        viki_logger.info(f"TestHealerPipeline: Started watching {watch_path}")

    def stop(self):
        """Stop the autonomous healing loop."""
        self.active = False
        if self._task:
            self._task.cancel()
            self._task = None
        viki_logger.info("TestHealerPipeline: Stopped")

    async def _run_loop(self):
        while self.active:
            try:
                await self._check_and_heal()
            except Exception as e:
                viki_logger.error(f"TestHealerPipeline Loop Error: {e}")
            
            await asyncio.sleep(self.interval)

    async def _check_and_heal(self):
        """Run tests and trigger healing on failure."""
        if not self.test_command or not self.watch_path:
            return

        viki_logger.info(f"TestHealerPipeline: Checking health of {self.watch_path}...")
        
        # 1. Run tests
        proc = await asyncio.create_subprocess_shell(
            self.test_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        if proc.returncode == 0:
            viki_logger.info("TestHealerPipeline: Tests passing. System healthy.")
            return

        # 2. Tests failed!
        viki_logger.warning("TestHealerPipeline: Test failure detected! Triggering MutationPilot HEAL...")
        error_log = stdout.decode() + "\n" + stderr.decode()
        
        # Identify target file (simple heuristic: first python file in watch_path if it's a file, or extract from log)
        target_file = self.watch_path
        if os.path.isdir(self.watch_path):
            # Try to find the file from the error log
            import re
            matches = re.findall(r'File "(.*?)", line', error_log)
            if matches:
                # Filter to only include files within the watch_path
                potential = [m for m in matches if m.startswith(os.path.abspath(self.watch_path))]
                if potential:
                    target_file = potential[-1] # Take the most recent file in the traceback
        
        # 3. Call MutationPilot heal action
        mutation_pilot = self.controller.skill_registry.get_skill('mutation_pilot')
        if not mutation_pilot:
            viki_logger.error("TestHealerPipeline: MutationPilot skill not found.")
            return

        result = await mutation_pilot.execute({
            "action": "heal",
            "path": target_file,
            "test_command": self.test_command,
            "error_log": error_log
        })

        if "HEAL_SUCCESS" in result:
            viki_logger.info(f"TestHealerPipeline: {result}")
            # Notify user via EventBus if available
            if hasattr(self.controller, 'nexus'):
                self.controller.nexus.emit("notification", {
                    "title": "Autonomous Repair Complete",
                    "message": f"Successfully healed {os.path.basename(target_file)} after test failure.",
                    "type": "success"
                })
        else:
            viki_logger.warning(f"TestHealerPipeline: Heal attempt failed. {result}")

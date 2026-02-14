
import asyncio
import time
import uuid
import heapq
import os
from typing import List, Dict, Any, Optional
from viki.config.logger import viki_logger
from viki.core.schema import VIKIResponse

import json
from enum import Enum

class MissionType(str, Enum):
    RESEARCH = "research"
    MAINTENANCE = "maintenance"
    MONITORING = "monitoring"
    CREATIVE = "creative"

class Mission:
    """
    A long-running proactive goal (Phase 6).
    """
    def __init__(self, description: str, priority: int = 50, m_type: MissionType = MissionType.MAINTENANCE, repeat_interval: int = 0):
        self.id = str(uuid.uuid4())[:8]
        self.description = description
        self.priority = priority 
        self.type = m_type
        self.status = "pending"
        self.created_at = time.time()
        self.last_check = 0
        self.repeat_interval = repeat_interval # 0 = one-off, >0 = seconds between runs
        self.progress = 0.0

    def to_dict(self):
        return {
            "id": self.id, "description": self.description, "priority": self.priority,
            "type": self.type, "status": self.status, "created_at": self.created_at,
            "last_check": self.last_check, "repeat_interval": self.repeat_interval,
            "progress": self.progress
        }

    @classmethod
    def from_dict(cls, data):
        m = cls(data["description"], data["priority"], data["type"], data.get("repeat_interval", 0))
        m.id = data["id"]
        m.status = data["status"]
        m.created_at = data["created_at"]
        m.last_check = data["last_check"]
        m.progress = data.get("progress", 0.0)
        return m

    def __lt__(self, other):
        return self.priority > other.priority

class MissionControl:
    """
    Phase 6: Autonomous Goal Governance.
    """
    def __init__(self, controller):
        self.controller = controller
        self.mission_queue = [] 
        self.active_missions: Dict[str, Mission] = {}
        self.is_running = False
        self.persistence_path = os.path.join(controller.settings.get('system', {}).get('data_dir', './data'), "missions.json")
        
        self._load_missions()

    def _load_missions(self):
        if os.path.exists(self.persistence_path):
            try:
                with open(self.persistence_path, 'r') as f:
                    data = json.load(f)
                    for m_data in data:
                        m = Mission.from_dict(m_data)
                        if m.status != 'complete':
                            heapq.heappush(self.mission_queue, m)
                            self.active_missions[m.id] = m
                viki_logger.info(f"Mission Control: Restored {len(self.active_missions)} missions.")
            except Exception as e:
                viki_logger.error(f"Failed to load missions: {e}")
        
        if not self.active_missions:
            self._hydrate_defaults()

    def _save_missions(self):
        try:
            data = [m.to_dict() for m in self.active_missions.values()]
            with open(self.persistence_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            viki_logger.error(f"Failed to save missions: {e}")

    def _hydrate_defaults(self):
        defaults = [
            ("Weekly Security Audit", 20, MissionType.MAINTENANCE, 604800),
            ("Daily Knowledge Synthesis", 40, MissionType.RESEARCH, 86400)
        ]
        for desc, prio, m_type, interval in defaults:
            self.add_mission(desc, prio, m_type, interval)

    def add_mission(self, description: str, priority: int = 50, m_type: MissionType = MissionType.MAINTENANCE, repeat_interval: int = 0):
        mission = Mission(description, priority, m_type, repeat_interval)
        heapq.heappush(self.mission_queue, mission)
        self.active_missions[mission.id] = mission
        self._save_missions()
        viki_logger.info(f"Mission Control: New Directive queued -> {description}")
        return mission.id

    async def start_loop(self):
        """Background autonomy loop."""
        self.is_running = True
        viki_logger.info("Mission Control: Autonomy Engine Engaged.")
        
        while self.is_running:
            try:
                # 1. Check for idle CPU cycles (don't interrupt user)
                if self.controller.signals.signals.get("cpu_load", 0) > 80:
                    await asyncio.sleep(60) 
                    continue

                if not self.mission_queue:
                    await asyncio.sleep(30)
                    continue

                # 2. Pick highest priority mission
                mission = self.mission_queue[0] # Peek
                
                # Check if it's time to run (e.g., cooldowns)
                interval = mission.repeat_interval if mission.repeat_interval > 0 else 3600
                if time.time() - mission.last_check < interval: 
                    await asyncio.sleep(10) # Quick spin
                    continue
                
                # 3. Execute Mission Step
                await self._step_mission(mission)
                
                # Re-heapify if priority changed (or just to be safe)
                heapq.heapify(self.mission_queue)
                
            except Exception as e:
                viki_logger.error(f"Mission Control failure: {e}")
                await asyncio.sleep(60)

    async def _step_mission(self, mission: Mission):
        viki_logger.info(f"Mission Control: Stepping '{mission.description}'...")
        mission.status = "active"
        mission.last_check = time.time()
        
        # Self-Prompting: Ask the Core what to do next for this mission
        prompt = (
            f"MISSION: {mission.description}\n"
            f"STATUS: {mission.progress:.1f}% Complete\n"
            f"GOAL: As an autonomous agent, execute the next logical step for this mission.\n"
            f"If complete, say so. If blocked, report it."
        )
        
        # We inject this into the controller as a "system" request
        # Note: We need a flag to prevent this from triggering strictly 'user' logic
        response = await self.controller.process_request(prompt) # Re-use core brain
        
        viki_logger.info(f"Mission '{mission.id}' Step Result: {response[:100]}...")
        
        # Simple heuristic completion check
        if "MISSION COMPLETE" in response.upper():
            if mission.repeat_interval > 0:
                mission.status = "pending" # Reset for next run
                viki_logger.info(f"Mission Control: Recurring Mission '{mission.description}' cycle complete.")
            else:
                mission.status = "complete"
                # Remove from active map but maybe keep in history? For now, pop.
                if mission.id in self.active_missions:
                     del self.active_missions[mission.id]
                # Re-heapify will handle the queue
                viki_logger.info(f"Mission Control: Mission '{mission.description}' COMPLETED.")
        
        self._save_missions()

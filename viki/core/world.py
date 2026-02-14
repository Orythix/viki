import os
import json
import time
from typing import Dict, Any, List
from viki.core.schema import WorldState
from viki.config.logger import viki_logger

class WorldModel:
    """
    v10: Persistent Internal model of the environment.
    Unlike Memory, this is absolute stateful understanding.
    """
    def __init__(self, data_path: str):
        self.path = os.path.join(data_path, "world_state.json")
        self.state = self._load()

    def _load(self) -> WorldState:
        if os.path.exists(self.path):
            try:
                with open(self.path, 'r') as f:
                    data = json.load(f)
                    return WorldState(**data)
            except:
                pass
        return WorldState()

    def save(self):
        self.state.last_updated = time.time()
        with open(self.path, 'w') as f:
            json.dump(self.state.model_dump(), f, indent=4)

    def track_app_usage(self, app_name: str, status: str = "known"):
        """Records installed apps and common statuses."""
        self.state.apps[app_name] = {
            "status": status,
            "last_used": time.time(),
            "count": self.state.apps.get(app_name, {}).get("count", 0) + 1
        }
        self.save()

    def define_safety_zone(self, path: str, tier: str):
        """Marks specific directories/apps with fixed stability/safety tiers."""
        self.state.safety_zones[path] = tier
        self.save()

    def map_path(self, path: str, purpose: str):
        """Maps a physical path to a semantic purpose (e.g. 'Project VIKI')."""
        self.state.semantic_paths[path] = purpose
        self.save()

    def add_habit(self, pattern: str, frequency: str = "occasional"):
        """Records a recurring user behavior for context injection."""
        self.state.user_habits.append({
            "pattern": pattern,
            "frequency": frequency,
            "recorded_at": time.time()
        })
        # Keep only latest 10 habits
        if len(self.state.user_habits) > 10:
            self.state.user_habits.pop(0)
        self.save()

    def get_understanding(self) -> str:
        """Returns a summarized textual prompt of the current world understanding."""
        apps = ", ".join(list(self.state.apps.keys())[:5])
        zones = ", ".join([f"{k}({v})" for k, v in list(self.state.safety_zones.items())[:3]])
        paths = ", ".join([f"{v}" for v in list(self.state.semantic_paths.values())[:5]])
        habits = ", ".join([h['pattern'] for h in self.state.user_habits[-3:]])
        
        understanding = f"WORLD MODEL AWARENESS:\n"
        if apps: understanding += f"- Identified Apps: {apps}\n"
        if paths: understanding += f"- Known Projects/Zones: {paths}\n"
        if habits: understanding += f"- Personal Habits: {habits}\n"
        if zones: understanding += f"- Safety Rules: {zones}\n"
        
        return understanding

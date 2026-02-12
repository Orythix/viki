import re
import time
import json
import os
from typing import Optional, Tuple, Dict, Any, List
from viki.core.schema import ActionCall
from viki.config.logger import viki_logger

class ReflexBrain:
    """
    The 'Reflex Brain' handles high-speed, low-latency intent recognition.
    It bypasses the heavy LLM for:
    - Exact phrase matches (Cache)
    - Simple Regex commands (OS Control, UI Navigation)
    - Learned patterns (from MetaCognition auto-learn)
    
    Response time target: < 200ms
    """
    def __init__(self, data_dir: str = None):
        self.intent_cache: Dict[str, str] = {}
        self.learned_patterns: Dict[str, Dict[str, Any]] = {}  # normalized_input -> {skill, params}
        self.data_dir = data_dir
        
        # Load learned patterns from disk
        if data_dir:
            self._load_learned()
        
        self.patterns = [
            # System Control - App Launching
            (r"^open\s+(?P<name>[\w\s]+)$", "system_control", {"action": "open_app", "name": "{name}"}),
            (r"^launch\s+(?P<name>[\w\s]+)$", "system_control", {"action": "open_app", "name": "{name}"}),
            
            # System Control - UI Interaction
            (r"^type\s+(?P<text>.+)$", "system_control", {"action": "type", "text": "{text}"}),
            (r"^click\s+(?P<x>\d+)\s+(?P<y>\d+)$", "system_control", {"action": "click", "x": "{x}", "y": "{y}"}),
            (r"^scroll\s+(?P<amount>-?\d+)$", "system_control", {"action": "scroll", "amount": "{amount}"}),
            (r"^press\s+(?P<key>\w+)$", "system_control", {"action": "press", "key": "{key}"}),

            # Browser / Research
            (r"^search\s+(?P<query>.+)$", "browser", {"action": "search", "query": "{query}"}),
            (r"^google\s+(?P<query>.+)$", "browser", {"action": "search", "query": "{query}"}),

            # Media Control
            (r"^pause.*$", "media_control", {"action": "play_pause"}),
            (r"^play.*$", "media_control", {"action": "play_pause"}),
            (r"^resume.*$", "media_control", {"action": "play_pause"}),
            (r"^stop\s+music.*$", "media_control", {"action": "stop"}),
            (r"^next\s+(track|song).*$", "media_control", {"action": "next_track"}),
            (r"^skip.*$", "media_control", {"action": "next_track"}),
            (r"^prev(ious)?\s+(track|song).*$", "media_control", {"action": "prev_track"}),
            (r"^mute.*$", "media_control", {"action": "mute"}),
            (r"^unmute.*$", "media_control", {"action": "mute"}),
            (r"^volume\s+up.*$", "media_control", {"action": "volume_up"}),
            (r"^volume\s+down.*$", "media_control", {"action": "volume_down"}),
        ]

    async def think(self, user_input: str, model_router: Optional[Any] = None) -> Tuple[Optional[str], Optional[ActionCall]]:
        """
        Process input through the Reflex Layer.
        Returns: (Response String, Action Object)
        If both are None, proceed to the Consciousness Stack (LLM).
        """
        clean_input = user_input.lower().strip()
        
        # 1. Cache Check (learned from previous LLM responses)
        if clean_input in self.intent_cache:
            return self.intent_cache[clean_input], None

        # 2. Learned Pattern Check (from MetaCognition auto-learn)
        normalized = ' '.join(clean_input.split())
        if normalized in self.learned_patterns:
            pattern = self.learned_patterns[normalized]
            viki_logger.info(f"Reflex: Learned pattern match for '{normalized}' -> {pattern['skill']}")
            return None, ActionCall(
                skill_name=pattern['skill'],
                parameters=pattern['params']
            )

        # 3. Regex Pattern Matching — System commands only
        for pattern, skill_name, params_template in self.patterns:
            match = re.search(pattern, clean_input)
            if match:
                try:
                    params = {}
                    groups = match.groupdict()
                    for k, v in params_template.items():
                        val = v.format(**groups)
                        if val.isdigit(): val = int(val)
                        params[k] = val
                    return None, ActionCall(skill_name=skill_name, parameters=params)
                except Exception: pass

        # No match — let the LLM handle it naturally
        return None, None

    def cache_intent(self, user_input: str, response: str):
        """Learn from the Thinker Brain's successful output."""
        if len(self.intent_cache) > 100:
            # FIFO eviction
            self.intent_cache.pop(next(iter(self.intent_cache)))
        self.intent_cache[user_input.lower().strip()] = response

    def learn_pattern(self, user_input: str, skill_name: str, params: dict):
        """Add a new learned pattern from MetaCognition's auto-learn.
        These persist across sessions."""
        normalized = ' '.join(user_input.lower().strip().split())
        self.learned_patterns[normalized] = {
            "skill": skill_name,
            "params": params,
            "learned_at": time.time(),
        }
        viki_logger.info(f"Reflex: Learned new pattern: '{normalized}' -> {skill_name}")
        self._save_learned()
    
    def get_learned_count(self) -> int:
        """Returns number of learned patterns."""
        return len(self.learned_patterns)
    
    def get_all_learned(self) -> List[Dict[str, Any]]:
        """Returns all learned patterns for display."""
        result = []
        for input_text, data in self.learned_patterns.items():
            result.append({
                "input": input_text,
                "skill": data["skill"],
                "params": data["params"],
                "learned_at": data.get("learned_at", 0),
            })
        return result

    def _save_learned(self):
        """Persist learned patterns to disk."""
        if not self.data_dir:
            return
        os.makedirs(self.data_dir, exist_ok=True)
        path = os.path.join(self.data_dir, "reflex_learned.json")
        try:
            with open(path, 'w') as f:
                json.dump(self.learned_patterns, f, indent=2)
        except Exception as e:
            viki_logger.warning(f"Failed to save learned patterns: {e}")
    
    def _load_learned(self):
        """Load learned patterns from disk."""
        if not self.data_dir:
            return
        path = os.path.join(self.data_dir, "reflex_learned.json")
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    self.learned_patterns = json.load(f)
                viki_logger.info(f"Reflex: Loaded {len(self.learned_patterns)} learned patterns")
            except Exception as e:
                viki_logger.warning(f"Failed to load learned patterns: {e}")
                self.learned_patterns = {}

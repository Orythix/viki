import random
import re
import time
import json
import os
from typing import Optional, Tuple, Dict, Any, List
from viki.core.schema import ActionCall
from viki.config.logger import viki_logger
from viki.core.utils.debouncer import SyncDebouncer


# Conversational reflexes — greetings / acks / farewells that should never need
# an LLM. Each entry is (compiled_regex, [response_options]). Responses rotate
# pseudo-randomly per call to avoid a robotic feel.
_CONVERSATIONAL_REFLEXES: List[Tuple[re.Pattern, List[str]]] = [
    (
        re.compile(r"^(hi|hello|hey|yo|hola|hiya)(\s+(there|viki))?[\.\!]*$", re.IGNORECASE),
        [
            "Hey. What can I do for you?",
            "Hi. Ready when you are.",
            "Hello. What's the task?",
        ],
    ),
    (
        re.compile(r"^good\s+(morning|afternoon|evening|night)(\s+viki)?[\.\!]*$", re.IGNORECASE),
        [
            "Good {tod}. How can I help?",
            "Good {tod} — what are we working on?",
        ],
    ),
    (
        re.compile(r"^(thanks|thank\s+you|thx|cheers|ty)(\s+viki)?[\.\!]*$", re.IGNORECASE),
        [
            "Anytime.",
            "Glad to help.",
            "You got it.",
        ],
    ),
    (
        re.compile(r"^(ok|okay|cool|nice|got\s+it|sounds\s+good|alright)[\.\!]*$", re.IGNORECASE),
        [
            "Acknowledged.",
            "Got it.",
            "Standing by.",
        ],
    ),
    (
        re.compile(r"^(bye|goodbye|see\s+ya|cya|later|farewell|good\s+night)[\.\!]*$", re.IGNORECASE),
        [
            "Catch you later.",
            "See you soon.",
            "Until next time.",
        ],
    ),
]

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
        self.blacklist: set = set()
        self.data_dir = data_dir
        
        # Debounce saves
        self._learned_debouncer = SyncDebouncer(delay=5.0, max_delay=30.0)
        self._blacklist_debouncer = SyncDebouncer(delay=5.0, max_delay=30.0)
        
        # Load learned patterns and blacklist from disk
        if data_dir:
            self._load_learned()
            self._load_blacklist()
        
        self.patterns = [
            # System Control - App Launching
            (r"^open\s+(?P<name>[\w\s]+)$", "system_control", {"action": "open_app", "name": "{name}"}),
            (r"^launch\s+(?P<name>[\w\s]+)$", "system_control", {"action": "open_app", "name": "{name}"}),
            
            # System Control - UI Interaction
            (r"^type\s+(?P<text>.+)$", "system_control", {"action": "type", "text": "{text}"}),
            (r"^click\s+(?P<x>\d+)\s+(?P<y>\d+)$", "system_control", {"action": "click", "x": "{x}", "y": "{y}"}),
            (r"^scroll\s+(?P<amount>-?\d+)$", "system_control", {"action": "scroll", "amount": "{amount}"}),
            (r"^press\s+(?P<key>\w+)$", "system_control", {"action": "press", "key": "{key}"}),

            # Browser / Research (Redirected to Headless Research)
            (r"^search\s+(?P<query>.+)$", "research", {"query": "{query}"}),
            (r"^google\s+(?P<query>.+)$", "research", {"query": "{query}"}),

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

            # Math (deterministic SafeMathEvaluator path)
            (
                r"^(?:calc(?:ulate)?|compute|eval(?:uate)?|what\s+is|whats|whatis)\s+(?P<expression>[\d\s\.\+\-\*\/\^\%\(\)\,e]+)\??$",
                "math_skill",
                {"expression": "{expression}"},
            ),
            (
                r"^(?P<expression>[\d\.\s]+\s*[\+\-\*\/\^\%]\s*[\d\.\s]+(?:\s*[\+\-\*\/\^\%]\s*[\d\.\s]+)*)\s*=?\s*\??$",
                "math_skill",
                {"expression": "{expression}"},
            ),
        ]

    def think(self, user_input: str) -> Tuple[Optional[str], Optional[ActionCall]]:
        """
        Process input through the Reflex Layer.
        Returns: (Response String, Action Object)
        If both are None, proceed to the Consciousness Stack (LLM).
        """
        clean_input = user_input.lower().strip()

        # Conversational reflex (greeting / ack / farewell). Runs BEFORE
        # the deliberation-deferral gate so "hi" / "hello viki" / "thanks"
        # never pay the LLM cold-start tax.
        canned = self._match_conversational_reflex(user_input)
        if canned is not None:
            return canned, None

        if self._should_defer_to_deliberation(clean_input):
            return None, None

        cached = self._get_cached_intent(clean_input)
        if cached is not None:
            return cached, None

        normalized = " ".join(clean_input.split())
        if normalized in self.blacklist:
            # Failed reflex patterns are forbidden from re-learning.
            return None, None

        learned_action = self._get_learned_action(normalized)
        if learned_action is not None:
            return None, learned_action

        # Regex pattern matching for simple system commands.
        return None, self._match_regex_action(clean_input)

    def _match_conversational_reflex(self, user_input: str) -> Optional[str]:
        """
        Match against `_CONVERSATIONAL_REFLEXES` and return a canned reply.
        Returns None if no match. Uses `random.choice` for a tiny bit of
        variety so VIKI doesn't sound like a copy-paste bot.
        """
        text = (user_input or "").strip()
        if not text or len(text) > 60:
            return None
        for regex, options in _CONVERSATIONAL_REFLEXES:
            m = regex.match(text)
            if not m:
                continue
            choice = random.choice(options)
            try:
                # Allow `{tod}` token substitution for "good morning" etc.
                tod = ""
                groups = m.groups()
                for g in groups:
                    if g and g.lower() in ("morning", "afternoon", "evening", "night"):
                        tod = g.lower()
                        break
                if "{tod}" in choice:
                    choice = choice.format(tod=tod or "day")
            except Exception:
                pass
            return choice
        return None

    def _should_defer_to_deliberation(self, clean_input: str) -> bool:
        """Reflex safety gate: questions go to the deliberation layer."""
        if "?" in clean_input:
            return True

        interrogatives = ["who", "what", "why", "when", "where", "how"]
        return any(clean_input.startswith(w + " ") or clean_input == w for w in interrogatives)

    def _get_cached_intent(self, clean_input: str) -> Optional[str]:
        """Return cached intent response when permitted."""
        if clean_input in self.intent_cache and clean_input not in self.blacklist:
            return self.intent_cache[clean_input]
        return None

    def _get_learned_action(self, normalized: str) -> Optional[ActionCall]:
        """Return a learned ActionCall when we have an exact normalized match."""
        if normalized not in self.learned_patterns:
            return None

        pattern = self.learned_patterns[normalized]
        viki_logger.info(f"Reflex: Learned pattern match for '{normalized}' -> {pattern['skill']}")
        return ActionCall(skill_name=pattern["skill"], parameters=pattern["params"])

    def _match_regex_action(self, clean_input: str) -> Optional[ActionCall]:
        """Try regex patterns for system commands; returns an ActionCall or None."""
        for pattern, skill_name, params_template in self.patterns:
            match = re.search(pattern, clean_input)
            if not match:
                continue

            try:
                params: Dict[str, Any] = {}
                groups = match.groupdict()
                for k, v in params_template.items():
                    val = v.format(**groups)
                    if val.isdigit():
                        val = int(val)
                    params[k] = val
                return ActionCall(skill_name=skill_name, parameters=params)
            except Exception as e:
                viki_logger.debug("Reflex pattern match: %s", e)

        return None

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

        # SAFEGUARD 1: Blacklist Check
        if normalized in self.blacklist:
            return

        # SAFEGUARD 2: Question Check
        # "Prohibited learning inputs: Any input that contains a question mark"
        if '?' in user_input:
            viki_logger.warning(f"Reflex: Refused to learn question pattern '{user_input}'")
            return
        
        # SAFEGUARD 3: Interrogative Intent
        # "Prohibited: Any interrogative intent such as who, what, why, when, where, how"
        interrogatives = ['who', 'what', 'why', 'when', 'where', 'how']
        if any(normalized.startswith(w + " ") or normalized == w for w in interrogatives):
             viki_logger.warning(f"Reflex: Refused to learn interrogative pattern '{user_input}'")
             return
        
        # SAFEGUARD 4: Length Check
        # "Prohibited: Any input longer than five words"
        if len(normalized.split()) > 5:
            viki_logger.warning(f"Reflex: Refused to learn long pattern '{user_input}'")
            return

        self.learned_patterns[normalized] = {
            "skill": skill_name,
            "params": params,
            "learned_at": time.time(),
        }
        viki_logger.info(f"Reflex: Learned new pattern: '{normalized}' -> {skill_name}")
        self._save_learned()
        
    def report_failure(self, user_input: str):
        """
        Handling rules:
        - Invalidate mapping immediately.
        - Forbidden from re-learning.
        """
        normalized = ' '.join(user_input.lower().strip().split())
        
        if normalized in self.learned_patterns:
            del self.learned_patterns[normalized]
            viki_logger.warning(f"Reflex: Invalidated failed pattern '{normalized}'")
            self._save_learned()
            
        self.blacklist.add(normalized)
        self._save_blacklist()
        viki_logger.info(f"Reflex: Blacklisted pattern '{normalized}' due to failure.")
    
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

    def _do_save_learned(self):
        """Internal method to actually save learned patterns."""
        if not self.data_dir:
            return
        os.makedirs(self.data_dir, exist_ok=True)
        path = os.path.join(self.data_dir, "reflex_learned.json")
        try:
            with open(path, 'w') as f:
                json.dump(self.learned_patterns, f, indent=2)
        except Exception as e:
            viki_logger.warning(f"Failed to save learned patterns: {e}")
    
    def _save_learned(self):
        """Debounced save for learned patterns."""
        self._learned_debouncer.mark_dirty()
        self._learned_debouncer.execute(self._do_save_learned)
    
    def flush_learned(self):
        """Force immediate save of learned patterns."""
        self._learned_debouncer.flush(self._do_save_learned)
    
    def _do_save_blacklist(self):
        """Internal method to actually save blacklist."""
        if not self.data_dir:
            return
        path = os.path.join(self.data_dir, "reflex_blacklist.json")
        try:
            with open(path, 'w') as f:
                json.dump(list(self.blacklist), f)
        except Exception as e:
            viki_logger.debug("Reflex save blacklist: %s", e)
            
    def _save_blacklist(self):
        """Debounced save for blacklist."""
        self._blacklist_debouncer.mark_dirty()
        self._blacklist_debouncer.execute(self._do_save_blacklist)
    
    def flush_blacklist(self):
        """Force immediate save of blacklist."""
        self._blacklist_debouncer.flush(self._do_save_blacklist)
    
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
                
    def _load_blacklist(self):
        if not self.data_dir: return
        path = os.path.join(self.data_dir, "reflex_blacklist.json")
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    self.blacklist = set(json.load(f))
            except Exception as e:
                viki_logger.debug("Reflex load blacklist: %s", e)

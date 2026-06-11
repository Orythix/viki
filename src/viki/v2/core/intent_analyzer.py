"""LLM-based semantic intent classification."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

SYSTEM_INTENT_EXAMPLES = [
    ("what is my wifi password", "network", {"action": "wifi_password"}),
    ("show me my wireless key", "network", {"action": "wifi_password"}),
    ("what network am I connected to", "network", {"action": "info"}),
    ("what os am i running", "system", {"query": "os"}),
    ("show my hardware specs", "system", {"query": "hardware"}),
    ("how much ram do i have", "system", {"query": "ram"}),
    ("list running processes", "system", {"query": "processes"}),
    ("what is my ip address", "network", {"action": "ip_address"}),
    ("ping google.com", "network", {"action": "ping", "target": "google.com"}),
    ("show disk info", "system", {"query": "disk"}),
]


class IntentAnalysis:
    def __init__(self, tool: str, params: dict, confidence: float, raw: str):
        self.tool = tool
        self.params = params
        self.confidence = confidence
        self.raw = raw


class IntentAnalyzer:
    def __init__(self):
        self._patterns: list[tuple[re.Pattern, str, dict]] = []

        for query, tool, params in SYSTEM_INTENT_EXAMPLES:
            pattern = re.compile(re.escape(query), re.IGNORECASE)
            self._patterns.append((pattern, tool, params))

    def analyze(self, user_input: str) -> IntentAnalysis | None:
        user_input = user_input.strip().lower()

        for pattern, tool, params in self._patterns:
            if pattern.search(user_input):
                return IntentAnalysis(
                    tool=tool,
                    params=dict(params),
                    confidence=0.95,
                    raw=user_input,
                )

        return None

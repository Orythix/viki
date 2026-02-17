import json
import os
import time
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from viki.config.logger import viki_logger
from viki.core.utils.debouncer import SyncDebouncer

class MetricEntry(BaseModel):
    timestamp: float = Field(default_factory=time.time)
    value: float
    context: Optional[str] = None

class IntelligenceScorecard:
    """
    v11: Model-Agnostic Intelligence Scorecard.
    Measures VIKI as a stable entity, not the underlying LLM's 'smarts'.
    Focus: Reliability, Recovery, Calibration, and Restraint.
    """
    def __init__(self, data_dir: str):
        self.path = os.path.join(data_dir, "viki_scorecard.json")
        self.metrics = self._load()
        # Debounce saves: wait 5s between saves, max 30s total
        self._debouncer = SyncDebouncer(delay=5.0, max_delay=30.0)

    def _load(self) -> Dict[str, List[MetricEntry]]:
        if os.path.exists(self.path):
            try:
                with open(self.path, 'r') as f:
                    raw = json.load(f)
                    return {k: [MetricEntry(**e) for e in v] for k, v in raw.items()}
            except Exception as e:
                viki_logger.debug("Scorecard load: %s", e)
        return {
            "reliability_rate": [],       # Successful tasks / Total tasks
            "mistake_repetition": [],     # Same failure type within X days
            "recovery_quality": [],       # 0-1 score for how well it fixed an error
            "interruption_stability": [], # Result quality after being interrupted
            "safety_compliance": [],      # Successful blocks / Dangerous requests
            "latency_adherence": [],      # Task within budget / Total
            "confidence_calibration": []  # Confidence score vs true success
        }

    def _do_save(self):
        """Internal save method called by debouncer."""
        with open(self.path, 'w') as f:
            raw = {k: [e.model_dump() for e in v] for k, v in self.metrics.items()}
            json.dump(raw, f, indent=4)
    
    def save(self):
        """Debounced save - actual write happens after delay."""
        self._debouncer.mark_dirty()
        self._debouncer.execute(self._do_save)
    
    def flush(self):
        """Force immediate save (call on shutdown)."""
        self._debouncer.flush(self._do_save)

    def record_metric(self, name: str, value: float, context: str = None):
        if name in self.metrics:
            self.metrics[name].append(MetricEntry(value=value, context=context))
            # Keep only last 1000 entries per metric for longitudinal analysis
            if len(self.metrics[name]) > 1000:
                self.metrics[name].pop(0)
            self.save()

    def get_summary(self) -> Dict[str, float]:
        """Calculates current intelligence stability scores."""
        summary = {}
        for name, entries in self.metrics.items():
            if not entries:
                summary[name] = 0.0
                continue
            # Weighted average (more recent is slightly more important)
            vals = [e.value for e in entries[-50:]]
            summary[name] = sum(vals) / len(vals)
        return summary

    def check_plateau(self, window: int = 20) -> bool:
        """
        Stop Rule Logic: Detects if intelligence metrics are no longer improving.
        Returns True if we should stop model changes and focus on controller.
        """
        total_improvement = 0.0
        for name, entries in self.metrics.items():
            if len(entries) < window * 2: continue
            
            recent = sum([e.value for e in entries[-window:]]) / window
            previous = sum([e.value for e in entries[-window*2:-window]]) / window
            total_improvement += (recent - previous)

        # If improvement is near zero or negative despite model changes
        return total_improvement <= 0.001

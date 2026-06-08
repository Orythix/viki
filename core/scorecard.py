import json
import os
import time
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from config.logger import viki_logger
from core.utils.debouncer import SyncDebouncer

class MetricEntry(BaseModel):
    timestamp: float = Field(default_factory=time.time)
    value: float
    context: Optional[str] = None
    # Phase 5: per-model segmentation. None = aggregate / unknown model.
    model: Optional[str] = None

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

    def record_metric(self, name: str, value: float, context: str = None, model: Optional[str] = None):
        if name in self.metrics:
            self.metrics[name].append(MetricEntry(value=value, context=context, model=model))
            # Keep only last 1000 entries per metric for longitudinal analysis
            if len(self.metrics[name]) > 1000:
                self.metrics[name].pop(0)
            self.save()

    def get_summary(self, model: Optional[str] = None) -> Dict[str, float]:
        """Calculates current intelligence stability scores, optionally per-model."""
        summary = {}
        for name, entries in self.metrics.items():
            if not entries:
                summary[name] = 0.0
                continue
            filtered = [e for e in entries if (model is None or e.model == model)]
            if not filtered:
                summary[name] = 0.0
                continue
            vals = [e.value for e in filtered[-50:]]
            summary[name] = sum(vals) / len(vals)
        return summary

    def get_segmented_summary(self) -> Dict[str, Dict[str, float]]:
        """
        Phase 5: per-model breakdown of every tracked metric. Useful for
        regression detection per provider (cloud vs. local) and for the
        promotion gate.
        """
        models: set = set()
        for entries in self.metrics.values():
            for e in entries:
                if e.model:
                    models.add(e.model)
        out: Dict[str, Dict[str, float]] = {"_all_": self.get_summary(None)}
        for m in sorted(models):
            out[m] = self.get_summary(m)
        return out

    def get_sparkline_series(
        self, points: int = 30, model: Optional[str] = None
    ) -> Dict[str, List[float]]:
        """
        P2: Return up to `points` recent values per metric for sparkline rendering.
        If `model` is provided, only entries tagged with that model are included.
        """
        out: Dict[str, List[float]] = {}
        for name, entries in self.metrics.items():
            filtered = [e for e in entries if (model is None or e.model == model)]
            tail = filtered[-points:]
            out[name] = [round(float(e.value), 4) for e in tail]
        return out

    def detect_regressions(
        self,
        window: int = 10,
        threshold: float = 0.05,
        model: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        P2: Compare the most recent `window` values against the previous window
        and flag metrics where the running mean dropped by more than `threshold`.
        """
        regressions: List[Dict[str, Any]] = []
        for name, entries in self.metrics.items():
            filtered = [e for e in entries if (model is None or e.model == model)]
            if len(filtered) < window * 2:
                continue
            recent = [e.value for e in filtered[-window:]]
            prev = [e.value for e in filtered[-window * 2:-window]]
            recent_mean = sum(recent) / len(recent)
            prev_mean = sum(prev) / len(prev)
            delta = recent_mean - prev_mean
            if delta < -abs(threshold):
                regressions.append({
                    "metric": name,
                    "recent_mean": round(recent_mean, 4),
                    "previous_mean": round(prev_mean, 4),
                    "delta": round(delta, 4),
                    "model": model,
                })
        return regressions

    def get_segmented_trends(
        self, points: int = 30, regression_window: int = 10, regression_threshold: float = 0.05
    ) -> Dict[str, Any]:
        """
        Bundle of (sparkline_series, regressions) per model, used by the dashboard
        scorecard panel. The aggregate is keyed `_all_`.
        """
        models: set = set()
        for entries in self.metrics.values():
            for e in entries:
                if e.model:
                    models.add(e.model)
        out: Dict[str, Any] = {
            "_all_": {
                "series": self.get_sparkline_series(points, None),
                "regressions": self.detect_regressions(
                    regression_window, regression_threshold, None
                ),
            }
        }
        for m in sorted(models):
            out[m] = {
                "series": self.get_sparkline_series(points, m),
                "regressions": self.detect_regressions(
                    regression_window, regression_threshold, m
                ),
            }
        return out

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

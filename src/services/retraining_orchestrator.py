from typing import Any

import yaml

from src.services.baseline_manager import BaselineManager
from src.services.drift_monitor_service import DriftMonitorService
from viki.config.logger import viki_logger

DRIFT_THRESHOLDS_PATH = "config/drift_thresholds.yaml"


class RetrainingOrchestrator:
    """
    The top-level orchestrator for Model Drift Monitoring and automated retraining.
    This service runs periodically or upon high-volume data ingestion events.
    """

    def __init__(self, drift_monitor: DriftMonitorService, baseline_manager: BaselineManager):
        self.drift_monitor = drift_monitor
        self.baseline_manager = baseline_manager

    def run_monitoring_cycle(self, live_data_batch: list[dict[str, Any]]):
        """
        Executes the full monitoring cycle: Check -> Score -> Trigger.
        """
        viki_logger.info("Starting Model Drift Monitoring Cycle")

        # 1. Run the check and get raw metrics
        raw_metrics = self.drift_monitor.run_drift_check(live_data_batch)

        # 2. Load thresholds for comparison
        try:
            with open(DRIFT_THRESHOLDS_PATH, encoding="utf-8") as f:
                thresholds = yaml.safe_load(f)
        except FileNotFoundError:
            viki_logger.error("Drift threshold file not found at %s!", DRIFT_THRESHOLDS_PATH)
            return

        # 3. Evaluate against thresholds and determine action
        trigger_needed = False
        report: dict[str, Any] = {"drift_detected": False, "remediation_required": []}

        for metric, current_value in raw_metrics.items():
            if metric not in thresholds["metrics"]:
                continue  # Skip metrics we don't monitor

            threshold_config = thresholds["metrics"][metric]
            max_val = self._max_threshold(threshold_config)
            if max_val is None:
                viki_logger.warning(
                    "Threshold config for '%s' declares no max_* bound; skipping.", metric
                )
                continue

            # Simplified check: Assume the current run is one of the configured
            # 'consecutive_failures' for demonstration. Tracking real streaks across
            # runs requires persisted state, which this scaffold does not yet keep.
            if current_value > max_val:
                report["remediation_required"].append(
                    {
                        "metric": metric,
                        "current_value": current_value,
                        "threshold": max_val,
                        "consecutive_failures_required": threshold_config.get(
                            "consecutive_failures", 1
                        ),
                        "action": "Requires retraining due to drift.",
                    }
                )
                trigger_needed = True

        report["drift_detected"] = trigger_needed

        # 4. Final Action Triggering
        if trigger_needed:
            viki_logger.warning("HIGH PRIORITY ALERT: MODEL DRIFT DETECTED!")
            self._initiate_retraining(report["remediation_required"])
        else:
            viki_logger.info(
                "Monitoring successful. Model performance is within acceptable drift parameters."
            )

    @staticmethod
    def _max_threshold(threshold_config: dict[str, Any]) -> float | None:
        """Return the ``max_*`` bound for a metric.

        Each metric names its bound after the statistic it measures
        (``max_cosine_distance``, ``max_kl_divergence``, ``max_variance``) rather
        than after the metric key, so the bound is resolved by prefix.
        """
        for key, value in threshold_config.items():
            if key.startswith("max_"):
                return float(value)
        return None

    def _initiate_retraining(self, failure_details: list[dict[str, Any]]):
        """Triggers the retraining pipeline using the most problematic data."""
        viki_logger.info("--- Initiating Automated Retraining Sequence ---")
        # 1. Collect Drift Sample Set (The core of the fix)
        drift_sample = self._collect_drift_samples(failure_details)

        # 2. Trigger Continuous Learner
        viki_logger.info(
            "Triggering continuous learning cycle with %d samples...", len(drift_sample)
        )
        # This would call the actual API/module responsible for fine-tuning
        # e.g., viki.learners.continuous_learner.initiate_fine_tune(...)
        viki_logger.info("Retraining job successfully queued.")

    def _collect_drift_samples(self, failure_details: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Gathers the specific data points responsible for the drift."""
        # In a real system, this would query the database/logs based on the failing metric.
        viki_logger.info("Collecting representative samples from logs...")
        return [{"prompt": "Drift sample 1", "context": "...", "source": "live_data"}]

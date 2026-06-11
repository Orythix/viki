import time
from typing import Any

from viki.config.logger import viki_logger


class CognitiveSignals:
    """
    v9: Emotion Simulation as Signal Processing.
    Emotions are not traits, but adaptive signals that modulate system behavior.
    """

    def __init__(self):
        self.signals: dict[str, float] = {
            "frustration": 0.0,  # Increases with corrections/failures
            "confidence": 0.5,  # Increases with repeated success
            "urgency": 0.0,  # Increases with time pressure
            "curiosity": 0.3,  # Increases with novelty
        }
        self.last_update = time.time()

    def update_signal(self, name: str, delta: float):
        if name in self.signals:
            self.signals[name] = max(0.0, min(1.0, self.signals[name] + delta))
            viki_logger.debug(f"Signal Update: {name} -> {self.signals[name]:.2f}")

    def decay_signals(self):
        """Natural return to baseline over time."""
        now = time.time()
        elapsed = now - self.last_update
        self.last_update = now

        decay_rate = 0.05 * (elapsed / 60)  # 5% per minute

        for name in self.signals:
            if name == "confidence":
                # Confidence is sticky, decays slower
                self.signals[name] = (
                    self.signals[name] - (decay_rate * 0.1)
                    if self.signals[name] > 0.5
                    else self.signals[name] + (decay_rate * 0.1)
                )
            else:
                self.signals[name] = max(0.0, self.signals[name] - decay_rate)

            self.signals[name] = max(0.0, min(1.0, self.signals[name]))

    def get_modulation(self) -> dict[str, Any]:
        """Calculates behavior modifiers based on current signals."""
        self.decay_signals()
        urgency = self.signals["urgency"]
        frustration = self.signals["frustration"]
        confidence = self.signals["confidence"]

        if urgency > 0.7:
            verbosity = "minimal"
        elif frustration > 0.5:
            verbosity = "detailed"
        else:
            verbosity = "standard"

        if frustration > 0.4:
            planning_depth = "deep"
        elif confidence > 0.8:
            planning_depth = "quick"
        else:
            planning_depth = "adaptive"

        safety_bias = "conservative" if frustration > 0.6 else "standard"

        return {
            "verbosity": verbosity,
            "planning_depth": planning_depth,
            "safety_bias": safety_bias,
        }

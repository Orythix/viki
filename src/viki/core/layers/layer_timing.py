"""Per-layer execution timing for MetaCognition analysis."""

from __future__ import annotations


class LayerTiming:
    """Tracks per-layer execution times for MetaCognition analysis."""

    def __init__(self):
        self.timings: dict[str, list[float]] = {}
        self.current_cycle: dict[str, float] = {}

    def record(self, layer_name: str, duration: float):
        if layer_name not in self.timings:
            self.timings[layer_name] = []
        self.timings[layer_name].append(duration)
        if len(self.timings[layer_name]) > 50:
            self.timings[layer_name].pop(0)
        self.current_cycle[layer_name] = duration

    def get_avg(self, layer_name: str) -> float:
        times = self.timings.get(layer_name, [])
        return sum(times) / len(times) if times else 0.0

    def get_total_current(self) -> float:
        return sum(self.current_cycle.values())

    def get_slowest(self) -> tuple[str, float]:
        if not self.current_cycle:
            return ("None", 0.0)
        name = max(self.current_cycle, key=lambda k: self.current_cycle[k])
        return (name, self.current_cycle[name])

    def reset_cycle(self):
        self.current_cycle.clear()

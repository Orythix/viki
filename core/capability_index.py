"""
Phase 2: Capability Index.

Aggregates per-suite normalized scores into one number that says, weekly,
whether VIKI is improving. Defined as the geometric mean of normalized
suite scores so a regression on any axis pulls the whole index down.

Each suite emits a result file at `data/eval_results/<suite>/<run_id>.jsonl`
where every line is one task outcome (`{task_id, score, passed, ...}`).
The index walks the latest run per suite and computes the four-axis score:

  coding   = mean(swe_bench_verified, humaneval_plus, livecodebench, bigcodebench)
  autonomy = mean(gaia, agentbench)
  reasoning = mean(mmlu_pro, gpqa_diamond, arc_agi)
  local_supremacy = mean(<any suite>:local_only_pass_rate)
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


# P2: minimum number of tasks required for a suite to count toward the
# index. Suites below this floor still appear in the breakdown but are
# tagged `qualifies=False` and excluded from axis aggregation. Set to
# `0` via env to disable for unit tests / synthetic fixtures.
DEFAULT_MIN_TASKS = int(os.environ.get("VIKI_CAPABILITY_MIN_TASKS", "20"))
DEFAULT_BOOTSTRAP_ITERS = int(os.environ.get("VIKI_CAPABILITY_BOOTSTRAP_ITERS", "300"))


SUITE_AXIS_MAP: Dict[str, str] = {
    "swe_bench_verified": "coding",
    "humaneval_plus": "coding",
    "livecodebench": "coding",
    "bigcodebench": "coding",
    "repobench": "coding",
    "gaia": "autonomy",
    "agentbench": "autonomy",
    "browsercomp": "autonomy",
    "webarena": "autonomy",
    "mmlu_pro": "reasoning",
    "gpqa_diamond": "reasoning",
    "arc_agi": "reasoning",
    # Local supremacy is *also* derived from any of the above, gated on the
    # `air_gap=true` flag in the results metadata.
}


@dataclass
class SuiteResult:
    suite: str
    run_id: str
    pass_rate: float
    mean_score: float
    task_count: int
    air_gap: bool = False
    timestamp: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    model: Optional[str] = None
    qualifies: bool = True
    ci_low: float = 0.0
    ci_high: float = 0.0
    provenance_sha256: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "suite": self.suite,
            "run_id": self.run_id,
            "pass_rate": round(self.pass_rate, 4),
            "mean_score": round(self.mean_score, 4),
            "task_count": self.task_count,
            "air_gap": self.air_gap,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "model": self.model,
            "qualifies": self.qualifies,
            "ci_low": round(self.ci_low, 4),
            "ci_high": round(self.ci_high, 4),
            "provenance_sha256": self.provenance_sha256,
        }


def _bootstrap_ci(passes: List[bool], iters: int = DEFAULT_BOOTSTRAP_ITERS,
                  seed: int = 1337) -> Tuple[float, float]:
    """
    P2: 95% bootstrap CI for the pass rate of a sample of bool outcomes.

    Returns (low, high) bounded to [0, 1]. Empty sample collapses to (0, 0).
    """
    n = len(passes)
    if n == 0:
        return 0.0, 0.0
    rng = random.Random(seed)
    samples: List[float] = []
    for _ in range(iters):
        boot = [passes[rng.randrange(n)] for _ in range(n)]
        samples.append(sum(1 for p in boot if p) / n)
    samples.sort()
    lo_i = max(0, int(0.025 * iters))
    hi_i = min(iters - 1, int(0.975 * iters))
    return samples[lo_i], samples[hi_i]


def _provenance_sha256(path: str) -> str:
    """Stable provenance hash so we can detect tampering / replays."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


MODEL_ID_KEYS = (
    "model",
    "model_name",
    "model_label",
    "model_profile",
    "profile",
    "default_model",
)


def _model_aliases(value: Any) -> Set[str]:
    """Return exact-match aliases for profile names and Ollama `:latest` tags."""
    if not isinstance(value, str):
        return set()
    raw = value.strip().lower()
    if not raw:
        return set()
    aliases = {raw}
    if raw.endswith(":latest"):
        aliases.add(raw[: -len(":latest")])
    elif ":" not in raw:
        aliases.add(f"{raw}:latest")
    return aliases


def _model_values(obj: Dict[str, Any]) -> List[str]:
    values: List[str] = []
    for key in MODEL_ID_KEYS:
        value = obj.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    return values


def _matches_model_filter(values: List[str], model_filter: Optional[str]) -> bool:
    if not model_filter:
        return True
    wanted = _model_aliases(model_filter)
    return any(_model_aliases(value) & wanted for value in values)


class CapabilityIndex:
    def __init__(
        self,
        results_root: str,
        min_tasks: int = DEFAULT_MIN_TASKS,
        bootstrap_iters: int = DEFAULT_BOOTSTRAP_ITERS,
        model_filter: Optional[str] = None,
    ):
        self.results_root = results_root
        self.min_tasks = max(0, int(min_tasks))
        self.bootstrap_iters = max(0, int(bootstrap_iters))
        self.model_filter = model_filter

    def latest_runs(self) -> List[SuiteResult]:
        """
        Walk `<root>/<suite>/` and pick the most recent `.jsonl` per suite.

        When `model_filter` is set, pick the most recent run in each suite that
        was explicitly tagged for that model/profile. Untagged legacy runs are
        ignored for model-scoped comparisons because they cannot prove which
        model produced the score.
        """
        runs: List[SuiteResult] = []
        if not os.path.isdir(self.results_root):
            return runs
        for suite in os.listdir(self.results_root):
            suite_dir = os.path.join(self.results_root, suite)
            if not os.path.isdir(suite_dir):
                continue
            jsonls = [f for f in os.listdir(suite_dir) if f.endswith(".jsonl")]
            if not jsonls:
                continue
            jsonls.sort(reverse=True)
            for latest in jsonls:
                run_path = os.path.join(suite_dir, latest)
                sr = self._load_run(suite, latest, run_path)
                if sr is not None:
                    runs.append(sr)
                    break
        return runs

    def _load_run(self, suite: str, run_id: str, path: str) -> Optional[SuiteResult]:
        try:
            scores: List[float] = []
            passes: List[bool] = []
            air_gap = False
            metadata: Dict[str, Any] = {}
            run_model_values: List[str] = []
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    if obj.get("__metadata__"):
                        metadata = obj
                        air_gap = bool(obj.get("air_gap", False))
                        run_model_values = _model_values(obj)
                        if (
                            self.model_filter
                            and run_model_values
                            and not _matches_model_filter(run_model_values, self.model_filter)
                        ):
                            return None
                        continue
                    row_model_values = _model_values(obj)
                    if self.model_filter:
                        if row_model_values:
                            if not _matches_model_filter(row_model_values, self.model_filter):
                                continue
                        elif not run_model_values:
                            continue
                    s = float(obj.get("score", 0.0))
                    scores.append(s)
                    passes.append(bool(obj.get("passed", s >= 0.5)))
            if not scores:
                return None
            iters = self.bootstrap_iters if self.bootstrap_iters > 0 else 0
            ci_low, ci_high = _bootstrap_ci(passes, iters) if iters else (0.0, 0.0)
            qualifies = len(scores) >= self.min_tasks
            return SuiteResult(
                suite=suite,
                run_id=run_id,
                pass_rate=sum(1 for p in passes if p) / len(passes),
                mean_score=sum(scores) / len(scores),
                task_count=len(scores),
                air_gap=air_gap,
                timestamp=os.path.getmtime(path),
                metadata=metadata,
                model=(run_model_values[0] if run_model_values else self.model_filter),
                qualifies=qualifies,
                ci_low=ci_low,
                ci_high=ci_high,
                provenance_sha256=_provenance_sha256(path),
            )
        except Exception:
            return None

    def compute(self) -> Dict[str, Any]:
        runs = self.latest_runs()
        per_axis: Dict[str, List[float]] = {"coding": [], "autonomy": [], "reasoning": []}
        local_only_scores: List[float] = []
        suite_breakdown: List[Dict[str, Any]] = []

        for sr in runs:
            axis = SUITE_AXIS_MAP.get(sr.suite)
            if axis and sr.qualifies:
                per_axis[axis].append(sr.pass_rate)
            if sr.air_gap and sr.qualifies:
                local_only_scores.append(sr.pass_rate)
            suite_breakdown.append(sr.as_dict())

        axis_scores: Dict[str, float] = {}
        for axis, vals in per_axis.items():
            axis_scores[axis] = (sum(vals) / len(vals)) if vals else 0.0
        axis_scores["local_supremacy"] = (
            sum(local_only_scores) / len(local_only_scores) if local_only_scores else 0.0
        )

        # Geometric mean of the four axes (with smoothing to keep zero from collapsing).
        smoothed = [max(0.001, axis_scores[a]) for a in ("coding", "autonomy", "reasoning", "local_supremacy")]
        capability_index = math.exp(sum(math.log(v) for v in smoothed) / len(smoothed))

        return {
            "capability_index": round(capability_index, 4),
            "axes": {k: round(v, 4) for k, v in axis_scores.items()},
            "suites": suite_breakdown,
            "computed_at": time.time(),
            "min_tasks_threshold": self.min_tasks,
            "qualifying_suites": sum(1 for s in suite_breakdown if s.get("qualifies")),
        }

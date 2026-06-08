import argparse
import asyncio
import datetime as _dt
import json
import os
import sys
import tempfile
from typing import Dict, Any, List

import yaml


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.append(REPO_ROOT)

from core.orchestrator import VIKIController
from core.performance_benchmark import ControlledBenchmark


def _load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _write_yaml(path: str, payload: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f)


async def run_once(
    settings_path: str,
    soul_path: str,
    suites: List[str],
    model_label: str,
    write_json: bool,
    output_dir: str,
) -> Dict[str, Any]:
    raw_settings = _load_yaml(settings_path)
    system = raw_settings.setdefault("system", {})

    run_data_dir = tempfile.mkdtemp(prefix="viki_superiority_")
    system["data_dir"] = run_data_dir

    # Keep the benchmark fast + deterministic (no external skill discovery).
    skills = raw_settings.setdefault("skills", {})
    skills.setdefault("auto_discover", False)
    skills.setdefault("registry_path", "")

    run_settings_path = os.path.join(run_data_dir, "settings_superiority_run.yaml")
    _write_yaml(run_settings_path, raw_settings)

    controller = VIKIController(run_settings_path, soul_path)
    benchmark = ControlledBenchmark(controller)

    suite_reports: Dict[str, Any] = {}
    all_results = []

    try:
        for suite in suites:
            results = await benchmark.run_suite(model_label=model_label, suite_name=suite)
            all_results.extend(results)
            suite_reports[suite] = benchmark.analyze_results(results)

        overall = benchmark.analyze_results(all_results)
    finally:
        try:
            controller.close()
        except Exception:
            pass
        try:
            await controller.shutdown()
        except Exception:
            pass

    now = _dt.datetime.now(tz=_dt.timezone.utc)
    report = {
        "timestamp": now.isoformat().replace("+00:00", "Z"),
        "model_label": model_label,
        "suites": suites,
        "suite_reports": suite_reports,
        "overall": overall,
        "air_gap": bool(raw_settings.get("system", {}).get("air_gap", False)),
    }

    if write_json:
        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(
            output_dir,
            f"superiority_report_{now.strftime('%Y%m%d_%H%M%S')}.json",
        )

        def _sync_write() -> None:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)

        await asyncio.to_thread(_sync_write)
        report["output_path"] = out_path

    return report


async def main():
    parser = argparse.ArgumentParser(description="Run VIKI ControlledBenchmark superiority eval.")
    parser.add_argument("--settings", default="./config/settings.yaml")
    parser.add_argument("--soul", default="./config/soul.yaml")
    parser.add_argument("--model-label", default="Current-VIKI")
    parser.add_argument("--suites", default="superiority,core,dev", help="Comma-separated suite names.")
    parser.add_argument("--no-write-json", action="store_true")
    parser.add_argument("--output-dir", default=os.path.join("tmp", "superiority_reports"))
    args = parser.parse_args()

    settings_path = args.settings
    soul_path = args.soul
    suites = [s.strip().lower() for s in args.suites.split(",") if s.strip()]

    write_json = not args.no_write_json

    report = await run_once(
        settings_path=settings_path,
        soul_path=soul_path,
        suites=suites,
        model_label=args.model_label,
        write_json=write_json,
        output_dir=args.output_dir,
    )

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())


"""
Build a VIKI model from learned lessons.

This is a thin, dependency-light orchestrator on top of the existing Neural
Forge pipeline (see viki/skills/creation/forge.py + viki/core/preference_forge.py):

  1. Pre-flight checks   -- Ollama daemon, base model, lesson count
  2. Dataset export      -- viki/core/learning.py:export_training_dataset (min access_count: --min-count, settings, VIKI_LESSON_EXPORT_MIN_ACCESS)
  3. Build               -- prompt-bake (default) | lora | dpo | orpo
  4. Verify              -- ollama show <tag>
  5. (optional) Promote  -- patch viki/config/models.yaml -> models.default

Strategies:

    prompt_bake (default, CPU-only)
        Writes data/Modelfile.viki_evolved with FROM <base> + a SYSTEM block
        carrying the top reinforced lessons, then runs `ollama create`.
        Produces an Ollama tag (default: viki-neural-forge; see settings / VIKI_FORGE_OUTPUT_OLLAMA_MODEL).

    lora (CUDA required)
        Runs Unsloth + TRL 4-bit LoRA SFT on the exported JSONL.
        Adapter saved to data/viki-lora-adapter/.

    dpo / orpo (CUDA required)
        Mines (prompt, chosen, rejected) triples and runs TRL DPO/ORPO.

Examples (PowerShell):

    # Default: CPU prompt-bake using qwen3.6:latest as the base
    python scripts/build_viki_model.py

    # Build and promote viki-evolved as the default profile
    python scripts/build_viki_model.py --set-default

    # GPU LoRA fine-tune (60 steps)
    $env:VIKI_UNSLOTH_RUN_TRAIN = "1"
    python scripts/build_viki_model.py --strategy lora --steps 60

    # GPU DPO preference tuning
    $env:VIKI_DPO_RUN_TRAIN = "1"
    python scripts/build_viki_model.py --strategy dpo
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

import yaml  # noqa: E402

from viki.core.forge_config import resolve_forge_output_ollama_tag  # noqa: E402

# ---------------------------------------------------------------------------
# Console helpers
# ---------------------------------------------------------------------------

USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else text


def step(n: int, total: int, msg: str) -> None:
    print(_c("1;36", f"\n[{n}/{total}] {msg}"))


def info(msg: str) -> None:
    print(f"  {msg}")


def ok(msg: str) -> None:
    print("  " + _c("32", "OK   ") + msg)


def warn(msg: str) -> None:
    print("  " + _c("33", "WARN ") + msg)


def fail(msg: str) -> str:
    print("  " + _c("31", "FAIL ") + msg)
    return msg


# ---------------------------------------------------------------------------
# Settings + path helpers
# ---------------------------------------------------------------------------


def load_settings() -> dict[str, Any]:
    settings_path = REPO_ROOT / "config" / "settings.yaml"
    with settings_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def resolve_base_model(cli_value: str | None, settings: dict[str, Any]) -> str:
    if cli_value:
        return cli_value.strip()
    env = (os.environ.get("VIKI_FORGE_BASE_OLLAMA_MODEL") or "").strip()
    if env:
        return env
    sysconf = settings.get("system") or {}
    return (sysconf.get("forge_base_ollama_model") or "qwen3.6:latest").strip()


def resolve_data_dir(cli_value: str | None, settings: dict[str, Any]) -> Path:
    if cli_value:
        d = Path(cli_value)
    else:
        env = os.environ.get("VIKI_DATA_DIR")
        if env:
            d = Path(env)
        else:
            sysconf = settings.get("system") or {}
            d = Path(sysconf.get("data_dir") or "./data")
    if not d.is_absolute():
        d = (REPO_ROOT / d).resolve()
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Ollama interaction
# ---------------------------------------------------------------------------


def _run(cmd: list[str], capture: bool = True, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        timeout=timeout,
        check=False,
    )


def ollama_available() -> tuple[bool, str]:
    if shutil.which("ollama") is None:
        return False, "`ollama` is not on PATH. Install from https://ollama.com/download."
    try:
        r = _run(["ollama", "list"], timeout=10)
    except Exception as e:
        return False, f"`ollama list` raised: {e!r}"
    if r.returncode != 0:
        return (
            False,
            f"Ollama daemon not reachable. Start it with `ollama serve`. stderr={r.stderr.strip()}",
        )
    return True, r.stdout


def ollama_has_model(tag: str) -> bool:
    try:
        r = _run(["ollama", "list"], timeout=10)
    except Exception:
        return False
    if r.returncode != 0:
        return False
    needle = tag.split(":")[0]
    for line in r.stdout.splitlines()[1:]:
        first = line.split()[0] if line.strip() else ""
        if first == tag or first.split(":")[0] == needle:
            return True
    return False


def ollama_create(tag: str, modelfile_path: Path) -> tuple[bool, str]:
    r = _run(["ollama", "create", tag, "-f", str(modelfile_path)], timeout=900)
    out = (r.stdout or "") + (r.stderr or "")
    return r.returncode == 0, out.strip()


def ollama_show(tag: str) -> str:
    r = _run(["ollama", "show", tag], timeout=15)
    return (r.stdout or r.stderr).strip()


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


def export_dataset(
    data_dir: Path,
    *,
    min_access_count: int,
    settings: dict[str, Any],
) -> tuple[Path, str]:
    from viki.core.knowledge_ingestion import LearningModule  # type: ignore

    dataset_path = data_dir / "training_dataset_lora.jsonl"
    learning = LearningModule(str(data_dir))
    summary = learning.export_training_dataset(
        str(dataset_path),
        format="jsonl",
        min_access_count=min_access_count,
        settings=settings,
    )
    return dataset_path, summary


def build_modelfile_content(base_model: str, lessons: list[str]) -> str:
    knowledge_block = "\n".join(f"- {lesson}" for lesson in lessons[-50:])
    return (
        f"FROM {base_model}\n"
        f'SYSTEM """\n'
        f"You are VIKI, a continuously evolving digital intelligence.\n"
        f"Here is your internalized knowledge base:\n"
        f"{knowledge_block}\n"
        f'"""\n'
        f"PARAMETER temperature 0.6\n"
        f'PARAMETER stop "<|eot_id|>"\n'
    )


def strategy_prompt_bake(
    *,
    base_model: str,
    tag: str,
    data_dir: Path,
    min_count: int,
    dry_run: bool,
) -> int:
    from viki.core.knowledge_ingestion import LearningModule  # type: ignore

    learning = LearningModule(str(data_dir))
    lessons = learning.get_frequent_lessons(min_count=min_count)
    if not lessons:
        fail(
            f"No lessons with access_count >= {min_count}. "
            "Use VIKI more (or lower --min-count) before forging."
        )
        return 2

    info(f"Reinforced lessons (min_count={min_count}): {len(lessons)}")
    modelfile_path = data_dir / "Modelfile.viki_evolved"
    modelfile_path.write_text(build_modelfile_content(base_model, lessons), encoding="utf-8")
    ok(f"Modelfile written -> {modelfile_path}")

    if dry_run:
        warn("--dry-run: skipping `ollama create`.")
        return 0

    info(f"Running: ollama create {tag} -f {modelfile_path.name}")
    success, out = ollama_create(tag, modelfile_path)
    if not success:
        fail("ollama create failed:")
        print(out)
        return 3
    ok(f"Ollama image '{tag}' built.")
    return 0


def strategy_lora(
    *,
    data_dir: Path,
    dataset_path: Path,
    steps: int,
    dry_run: bool,
) -> int:
    if (os.environ.get("VIKI_UNSLOTH_RUN_TRAIN") or "").lower() not in ("1", "true", "yes"):
        warn(
            "VIKI_UNSLOTH_RUN_TRAIN is not set. Dataset is exported but training is "
            "skipped. Set VIKI_UNSLOTH_RUN_TRAIN=1 to actually run LoRA."
        )
        return 0

    if dry_run:
        warn("--dry-run: skipping LoRA training.")
        return 0

    try:
        from viki.skills.creation.forge import _unsloth_train_sync  # type: ignore
    except Exception as e:
        fail(f"Cannot import LoRA trainer: {e!r}")
        return 4

    settings = load_settings()
    info(f"LoRA training: dataset={dataset_path.name}, steps={steps}")
    msg = _unsloth_train_sync(
        data_dir=str(data_dir),
        dataset_path=str(dataset_path),
        params={"steps": int(steps)},
        settings=settings,
        summary=f"dataset={dataset_path.name}",
    )
    print(msg)
    if "adapter saved" in msg.lower():
        ok(f"Adapter dir: {data_dir / 'viki-lora-adapter'}")
        return 0
    fail("LoRA training did not complete cleanly.")
    return 5


async def _run_dpo_async(
    *,
    method: str,
    data_dir: Path,
    steps: int,
    dry_run: bool,
) -> int:
    try:
        from viki.core.knowledge_ingestion import LearningModule  # type: ignore
        from viki.core.preference_forge import (  # type: ignore
            PreferenceDatasetBuilder,
            run_dpo_training,
            trl_dpo_available,
        )
    except Exception as e:
        fail(f"Cannot import preference forge: {e!r}")
        return 4

    learning = LearningModule(str(data_dir))
    pref_path = data_dir / "preference_dataset.jsonl"
    builder = PreferenceDatasetBuilder(learning)
    summary, n = builder.build(str(pref_path), max_pairs=500)
    info(f"Preference dataset: {summary} ({n} pairs) -> {pref_path.name}")

    if n == 0:
        fail("No preference pairs available; use VIKI more or lower thresholds.")
        return 6

    run = (os.environ.get("VIKI_DPO_RUN_TRAIN") or "").lower() in ("1", "true", "yes")
    if not run:
        warn(
            "VIKI_DPO_RUN_TRAIN is not set. Preference dataset exported but training "
            "is skipped. Set VIKI_DPO_RUN_TRAIN=1 plus VIKI_UNSLOTH_BASE_MODEL to "
            "actually run DPO/ORPO."
        )
        return 0

    if not trl_dpo_available():
        fail(
            "TRL/DPO stack not importable. Install: pip install trl transformers "
            "datasets accelerate peft unsloth (CUDA required)."
        )
        return 7

    if dry_run:
        warn("--dry-run: skipping DPO training.")
        return 0

    base = (
        os.environ.get("VIKI_UNSLOTH_BASE_MODEL", "").strip()
        or "unsloth/Qwen2.5-3B-Instruct-bnb-4bit"
    )
    info(f"{method.upper()} training: base={base}, steps={steps}")
    out_dir = data_dir / f"viki-{method}-adapter"
    msg = await asyncio.to_thread(
        run_dpo_training,
        dataset_path=str(pref_path),
        base_model_id=base,
        output_dir=str(out_dir),
        method=method,
        steps=int(steps),
    )
    print(msg)
    return 0


def strategy_preference(
    *,
    method: str,
    data_dir: Path,
    steps: int,
    dry_run: bool,
) -> int:
    return asyncio.run(
        _run_dpo_async(method=method, data_dir=data_dir, steps=steps, dry_run=dry_run)
    )


# ---------------------------------------------------------------------------
# Optional: promote viki-evolved as the default profile
# ---------------------------------------------------------------------------


def set_default_profile(profile_name: str = "viki-evolved") -> bool:
    models_yaml = REPO_ROOT / "config" / "models.yaml"
    try:
        text = models_yaml.read_text(encoding="utf-8")
    except FileNotFoundError:
        fail(f"{models_yaml} not found.")
        return False

    new_text = []
    changed = False
    for line in text.splitlines():
        if line.strip().startswith("default:") and not changed:
            indent = line[: len(line) - len(line.lstrip())]
            new_text.append(f"{indent}default: {profile_name}")
            changed = True
        else:
            new_text.append(line)
    if not changed:
        warn("Could not locate `default:` in models.yaml; leaving file unchanged.")
        return False
    models_yaml.write_text("\n".join(new_text) + "\n", encoding="utf-8")
    ok(f"models.yaml -> default: {profile_name}")
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="build_viki_model",
        description="Build a VIKI model from learned lessons (prompt-bake / LoRA / DPO / ORPO).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--strategy",
        choices=["prompt_bake", "lora", "dpo", "orpo"],
        default="prompt_bake",
        help="Training strategy. prompt_bake works on CPU; lora/dpo/orpo require CUDA.",
    )
    p.add_argument(
        "--name",
        default=None,
        help="Output Ollama tag (prompt_bake). Default: forge_output_ollama_tag / VIKI_FORGE_OUTPUT_OLLAMA_MODEL / viki-neural-forge.",
    )
    p.add_argument(
        "--base", default=None, help="Base Ollama model (FROM line). Defaults to settings/env."
    )
    p.add_argument("--steps", type=int, default=60, help="Training steps (lora/dpo/orpo).")
    p.add_argument(
        "--min-count",
        type=int,
        default=2,
        help="Min lesson access_count for prompt-bake and for JSONL export (unless overridden in settings/env).",
    )
    p.add_argument("--data-dir", default=None, help="VIKI data dir. Defaults to settings/env.")
    p.add_argument("--no-export", action="store_true", help="Skip JSONL dataset export step.")
    p.add_argument(
        "--set-default", action="store_true", help="Patch models.yaml -> default: viki-evolved."
    )
    p.add_argument(
        "--dry-run", action="store_true", help="Run all checks but skip ollama create / training."
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    print(_c("1;35", "===  VIKI Neural Forge  ==="))
    print(_c("90", f"repo: {REPO_ROOT}"))

    settings = load_settings()
    data_dir = resolve_data_dir(args.data_dir, settings)
    base_model = resolve_base_model(args.base, settings)
    forge_tag = (args.name or "").strip() or resolve_forge_output_ollama_tag(settings)

    info(f"strategy   : {args.strategy}")
    info(f"data dir   : {data_dir}")
    info(f"base model : {base_model}")
    if args.strategy == "prompt_bake":
        info(f"output tag : {forge_tag}")

    total_steps = 4 + (1 if args.set_default else 0)

    step(1, total_steps, "Pre-flight checks")
    if args.strategy == "prompt_bake" or args.set_default:
        avail, out = ollama_available()
        if not avail:
            fail(out)
            return 1
        ok("Ollama daemon reachable.")
        if not ollama_has_model(base_model):
            fail(f"Base model '{base_model}' not found locally. Run: ollama pull {base_model}")
            return 1
        ok(f"Base model present: {base_model}")
    else:
        info("Skipping Ollama check for GPU strategy (training stack only).")

    try:
        from viki.core.knowledge_ingestion import LearningModule  # type: ignore
    except Exception as e:
        fail(f"Cannot import VIKI internals (run from repo root, deps installed): {e!r}")
        return 1
    learning = LearningModule(str(data_dir))
    total = learning.get_total_lesson_count()
    info(f"Total lessons in DB: {total}")
    if total == 0:
        fail("No lessons recorded yet. Use VIKI for a few sessions first.")
        return 1
    ok("Knowledge base reachable.")

    step(2, total_steps, "Export training dataset")
    if args.no_export:
        warn("--no-export: skipped.")
    else:
        dataset_path, summary = export_dataset(
            data_dir,
            min_access_count=args.min_count,
            settings=settings,
        )
        info(summary)
        ok(f"Dataset -> {dataset_path}")

    step(3, total_steps, f"Build ({args.strategy})")
    rc: int
    if args.strategy == "prompt_bake":
        rc = strategy_prompt_bake(
            base_model=base_model,
            tag=forge_tag,
            data_dir=data_dir,
            min_count=args.min_count,
            dry_run=args.dry_run,
        )
    elif args.strategy == "lora":
        dataset_path = data_dir / "training_dataset_lora.jsonl"
        if not dataset_path.exists():
            dataset_path, _ = export_dataset(
                data_dir,
                min_access_count=args.min_count,
                settings=settings,
            )
        rc = strategy_lora(
            data_dir=data_dir,
            dataset_path=dataset_path,
            steps=args.steps,
            dry_run=args.dry_run,
        )
    else:
        rc = strategy_preference(
            method=args.strategy,
            data_dir=data_dir,
            steps=args.steps,
            dry_run=args.dry_run,
        )

    if rc != 0:
        return rc

    step(4, total_steps, "Verify build")
    if args.strategy == "prompt_bake" and not args.dry_run:
        details = ollama_show(forge_tag)
        if details and "Error" not in details.split("\n", 1)[0]:
            print(_c("90", details[:600]))
            ok(f"Verified: ollama tag '{forge_tag}' exists.")
        else:
            warn("Could not verify Ollama tag (see output above).")
    else:
        info("Verification only applies to prompt_bake builds.")

    if args.set_default:
        step(5, total_steps, "Promote viki-evolved as default profile")
        set_default_profile("viki-evolved")

    print(_c("1;32", "\nDone."))
    print(_c("90", "Next steps:"))
    if args.strategy == "prompt_bake":
        print(f"  - Try it directly: ollama run {forge_tag}")
        if not args.set_default:
            print("  - To use it as VIKI's default, edit viki/config/models.yaml:")
            print("       default: viki-evolved")
            print("    or rerun with --set-default.")
    elif args.strategy == "lora":
        print(f"  - Adapter at: {data_dir / 'viki-lora-adapter'}")
        print("  - Convert to GGUF and create an Ollama Modelfile with `ADAPTER` to serve it.")
    else:
        print(f"  - Adapter at: {data_dir / f'viki-{args.strategy}-adapter'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted.")
        raise SystemExit(130) from None

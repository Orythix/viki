"""Neural Forge LoRA pipeline: real fine-tuning on accumulated lessons.

Upgrades the Forge from prompt-baking to actual parameter-level
learning. Three stages, each usable independently:

1. ``LoraDatasetExporter`` — turns the SQLite lessons store into a
   chat-format JSONL training set.
2. ``LoraTrainer`` — runs LoRA fine-tuning via peft/trl. The heavy ML stack
   (torch, transformers, peft, trl, datasets) is imported lazily; on machines
   without it the trainer reports clearly instead of crashing.
3. ``write_adapter_modelfile`` — emits a reference Modelfile that loads the
   trained adapter on top of the base model.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any

from viki.config.logger import viki_logger

_DEFAULT_SYSTEM_PROMPT = (
    "You are VIKI, a sovereign digital intelligence evolved from user interaction."
)


@dataclass
class LoraConfig:
    """Configuration for a Forge LoRA run."""

    base_model: str = "microsoft/Phi-3-mini-4k-instruct"
    output_dir: str = "data/forge/lora"
    rank: int = 16
    alpha: int = 32
    dropout: float = 0.05
    epochs: int = 3
    learning_rate: float = 2e-4
    max_seq_length: int = 1024
    min_reliability: float = 0.5
    min_lesson_chars: int = 20
    max_lessons: int = 2000
    system_prompt: str = _DEFAULT_SYSTEM_PROMPT
    target_modules: list[str] = field(
        default_factory=lambda: ["q_proj", "k_proj", "v_proj", "o_proj"]
    )


class LoraDatasetExporter:
    """Exports lessons from the learning DB into a chat-format JSONL dataset.

    Each lesson becomes one example. Lessons stored as ``{"trigger": ...,
    "fact": ...}`` map naturally onto a user/assistant turn; free-text lessons
    become recall-style examples.
    """

    def __init__(self, conn: sqlite3.Connection, config: LoraConfig | None = None):
        self.conn = conn
        self.config = config or LoraConfig()

    def _rows(self) -> list[sqlite3.Row]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT content, text_representation, reliability, source_task
            FROM lessons
            WHERE COALESCE(reliability, 1.0) >= ?
            ORDER BY COALESCE(access_count, 1) DESC, created_at DESC
            LIMIT ?
            """,
            (self.config.min_reliability, self.config.max_lessons),
        )
        return cur.fetchall()

    def _to_example(self, row: sqlite3.Row) -> dict[str, Any] | None:
        text = (row["text_representation"] or "").strip()
        if len(text) < self.config.min_lesson_chars:
            return None

        trigger, fact = None, None
        raw = row["content"]
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    trigger = (parsed.get("trigger") or "").strip() or None
                    fact = (parsed.get("fact") or "").strip() or None
            except (ValueError, TypeError):
                pass

        if trigger and fact:
            user_msg, assistant_msg = trigger, fact
        else:
            user_msg = f"What do you know about this? {text[:120]}"
            assistant_msg = text

        return {
            "messages": [
                {"role": "system", "content": self.config.system_prompt},
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": assistant_msg},
            ]
        }

    def export(self, path: str) -> int:
        """Write the JSONL dataset. Returns number of examples written."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        count = 0
        seen: set[str] = set()
        with open(path, "w", encoding="utf-8") as f:
            for row in self._rows():
                ex = self._to_example(row)
                if ex is None:
                    continue
                key = ex["messages"][2]["content"][:200]
                if key in seen:
                    continue
                seen.add(key)
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")
                count += 1
        viki_logger.info("Forge LoRA: exported %d training examples to %s", count, path)
        return count


def ml_stack_available() -> tuple[bool, str]:
    """Check whether the optional fine-tuning stack is importable.

    Import order matters here: on some Windows installs, importing ``peft``
    (or ``trl``) before ``datasets`` triggers a native DLL conflict (pyarrow
    vs. torch's bundled OpenMP runtime) that segfaults the whole process
    instead of raising ImportError. ``datasets`` must load first — this
    mirrors the working order used by ``LoraTrainer.train``.
    """
    missing = []
    for mod in ("torch", "datasets", "peft", "transformers", "trl"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        return False, (
            "LoRA fine-tuning requires the ML stack. Missing: "
            + ", ".join(missing)
            + ". Install with: pip install "
            + " ".join(missing)
        )
    return True, "ok"


class LoraTrainer:
    """Runs LoRA fine-tuning over an exported dataset.

    Heavy imports happen inside ``train`` so that importing this module (and
    the Forge) stays cheap on machines without the ML stack.
    """

    def __init__(self, config: LoraConfig | None = None):
        self.config = config or LoraConfig()

    def train(self, dataset_path: str) -> dict[str, Any]:
        """Train an adapter. Returns a result dict with status and paths."""
        ok, reason = ml_stack_available()
        if not ok:
            viki_logger.warning("Forge LoRA: %s", reason)
            return {"status": "unavailable", "reason": reason}

        import torch
        from datasets import load_dataset
        from peft import LoraConfig as PeftLoraConfig
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from trl import SFTConfig, SFTTrainer

        cfg = self.config
        t0 = time.time()
        os.makedirs(cfg.output_dir, exist_ok=True)

        # Decide the training device ourselves instead of device_map="auto":
        # accelerate's auto-offload path wraps forward() in a functools.partial
        # for any layers it puts on the meta device, which crashes trl's
        # chunked-CE patch (`_patch_chunked_ce_lm_head` expects a bound method).
        # A single explicit device sidesteps that entirely.
        free_bytes = 0
        if torch.cuda.is_available():
            free_bytes, _total = torch.cuda.mem_get_info()
        use_cuda = free_bytes > 9 * 1024**3  # headroom for weights + LoRA overhead
        device = "cuda" if use_cuda else "cpu"
        dtype = torch.bfloat16 if use_cuda else torch.float32

        viki_logger.info("Forge LoRA: loading base model '%s' on %s...", cfg.base_model, device)
        tokenizer = AutoTokenizer.from_pretrained(cfg.base_model)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        model = AutoModelForCausalLM.from_pretrained(cfg.base_model, dtype=dtype)
        model.to(device)

        dataset = load_dataset("json", data_files=dataset_path, split="train")

        peft_config = PeftLoraConfig(
            r=cfg.rank,
            lora_alpha=cfg.alpha,
            lora_dropout=cfg.dropout,
            target_modules=cfg.target_modules,
            task_type="CAUSAL_LM",
        )
        sft_config = SFTConfig(
            output_dir=cfg.output_dir,
            num_train_epochs=cfg.epochs,
            learning_rate=cfg.learning_rate,
            max_length=cfg.max_seq_length,
            per_device_train_batch_size=1,
            gradient_accumulation_steps=4,
            logging_steps=10,
            save_strategy="epoch",
            report_to=[],
            use_cpu=not use_cuda,
        )
        trainer = SFTTrainer(
            model=model,
            processing_class=tokenizer,
            train_dataset=dataset,
            peft_config=peft_config,
            args=sft_config,
        )
        trainer.train()
        adapter_dir = os.path.join(cfg.output_dir, "adapter")
        trainer.save_model(adapter_dir)

        elapsed = time.time() - t0
        viki_logger.info("Forge LoRA: training complete in %.1fs → %s", elapsed, adapter_dir)
        return {
            "status": "trained",
            "adapter_dir": adapter_dir,
            "examples": len(dataset),
            "seconds": round(elapsed, 1),
        }


def write_adapter_modelfile(
    base_model_tag: str,
    adapter_dir: str,
    path: str,
    system_prompt: str = _DEFAULT_SYSTEM_PROMPT,
) -> str:
    """Write a Modelfile that loads the LoRA adapter (reference for LM Studio).

    ``base_model_tag`` is the model id (e.g. ``google/gemma-4-e4b``); ``adapter_dir``
    is the directory produced by :class:`LoraTrainer`.
    """
    content = (
        f"FROM {base_model_tag}\n"
        f"ADAPTER {os.path.abspath(adapter_dir)}\n"
        f'SYSTEM """\n{system_prompt}\n"""\n'
        "PARAMETER temperature 0.7\n"
    )
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    viki_logger.info("Forge LoRA: wrote adapter Modelfile → %s", path)
    return path


class AutoLoraForgeService:
    """
    Background service that monitors accumulated SQLite lessons and automatically
    exports JSONL datasets and queues LoRA fine-tuning when new lesson thresholds are met.
    """

    def __init__(self, conn: sqlite3.Connection, config: LoraConfig | None = None):
        self.exporter = LoraDatasetExporter(conn, config)
        self.trainer = LoraTrainer(config)
        self.config = config or LoraConfig()

    def check_and_export(
        self, jsonl_out_path: str = "data/forge/auto_dataset.jsonl"
    ) -> dict[str, Any]:
        """Exports dataset if enough lessons exist in SQLite."""
        os.makedirs(os.path.dirname(jsonl_out_path) or ".", exist_ok=True)
        count = self.exporter.export(jsonl_out_path)
        return {
            "status": "exported",
            "jsonl_path": jsonl_out_path,
            "examples_count": count,
        }

    def trigger_auto_forge(self, jsonl_path: str) -> dict[str, Any]:
        """Triggers LoRA dataset training."""
        return self.trainer.train(jsonl_path)

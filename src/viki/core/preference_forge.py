"""
Preference-tuning Forge (Phase 5).

Replaces the prompt-baking default with real preference optimization:

    * Builds (prompt, chosen, rejected) triples from the LearningModule
      (positives) and the Failure Memory (negatives).
    * Optionally augments with "teacher distillation" pairs where a frontier
      cloud model rewrites a hard prompt and the original local response is
      treated as the rejected sample. Distillation is gated by an explicit
      `system.allow_distillation` flag plus per-prompt user consent.
    * Drives DPO/ORPO via TRL when CUDA + dependencies are available.
    * When the heavy training stack is missing, exports a JSONL preference
      dataset and reports a clear remediation message instead of crashing.

The Modelfile prompt-bake path remains as a cold-start fallback for first-run
machines without GPUs; the eval-gated promotion module decides which artifact
becomes `models.default`.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from viki.config.logger import viki_logger


@dataclass
class PreferencePair:
    """A single DPO/ORPO training row."""

    prompt: str
    chosen: str
    rejected: str
    source: str = "memory"  # "memory" | "failure" | "teacher"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt": self.prompt,
            "chosen": self.chosen,
            "rejected": self.rejected,
            "source": self.source,
            "metadata": self.metadata,
        }


class PreferenceDatasetBuilder:
    """
    Mines positive / negative pairs from the LearningModule's SQLite store and
    emits a JSONL file ready for TRL's DPOTrainer / ORPOTrainer.
    """

    def __init__(self, learning_module: Any):
        self.learning = learning_module

    def build(
        self,
        output_path: str,
        max_pairs: int = 500,
        teacher_pairs: Optional[Iterable[PreferencePair]] = None,
    ) -> Tuple[str, int]:
        pairs: List[PreferencePair] = []
        pairs.extend(self._mine_failure_pairs(limit=max_pairs))
        pairs.extend(self._mine_lesson_pairs(limit=max_pairs))
        if teacher_pairs:
            pairs.extend(list(teacher_pairs))

        if not pairs:
            return "No preference pairs available.", 0

        pairs = pairs[:max_pairs]

        os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for p in pairs:
                f.write(json.dumps(p.to_dict(), ensure_ascii=False) + "\n")
        viki_logger.info(
            "PreferenceDatasetBuilder: wrote %d pairs to %s",
            len(pairs),
            output_path,
        )
        return f"Wrote {len(pairs)} preference pairs to {output_path}.", len(pairs)

    def _mine_failure_pairs(self, limit: int) -> List[PreferencePair]:
        """
        For every failure in the failures table, treat the failed action as the
        rejected response and (if available) the relevant lesson as the chosen.
        """
        if self.learning is None or not hasattr(self.learning, "conn"):
            return []
        try:
            cur: sqlite3.Cursor = self.learning.conn.cursor()
            cur.execute(
                "SELECT action, error, context, timestamp FROM failures ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
            rows = cur.fetchall()
        except Exception as e:
            viki_logger.debug("PreferenceDatasetBuilder: failure mining failed: %s", e)
            return []

        out: List[PreferencePair] = []
        for r in rows:
            ctx = r["context"] if "context" in r.keys() else r[2]
            action = r["action"] if "action" in r.keys() else r[0]
            error = r["error"] if "error" in r.keys() else r[1]
            prompt = (ctx or "").strip()
            if not prompt:
                continue
            chosen = self._best_lesson_for(prompt) or "Decline politely and request the missing info."
            rejected = (
                f"{action}\n# error: {error}" if action else f"# error: {error}"
            ).strip() or "(failed action with no detail)"
            out.append(
                PreferencePair(
                    prompt=prompt,
                    chosen=chosen,
                    rejected=rejected,
                    source="failure",
                )
            )
        return out

    def _mine_lesson_pairs(self, limit: int) -> List[PreferencePair]:
        """
        Synthetic positives only: turn each high-confidence lesson into a
        (lesson trigger -> lesson fact) pair where the rejected sample is a
        terse "I don't know" baseline. This anchors the model toward recalling
        its own learned facts.
        """
        if self.learning is None or not hasattr(self.learning, "conn"):
            return []
        try:
            cur = self.learning.conn.cursor()
            cur.execute(
                "SELECT text_representation, content FROM lessons WHERE access_count >= 2 "
                "ORDER BY last_accessed DESC LIMIT ?",
                (limit,),
            )
            rows = cur.fetchall()
        except Exception as e:
            viki_logger.debug("PreferenceDatasetBuilder: lesson mining failed: %s", e)
            return []

        out: List[PreferencePair] = []
        for r in rows:
            try:
                obj = json.loads(r["content"]) if r["content"] else {}
            except Exception:
                obj = {}
            trigger = (obj.get("trigger") or "").strip()
            fact = (obj.get("fact") or r["text_representation"] or "").strip()
            if not trigger or not fact:
                continue
            out.append(
                PreferencePair(
                    prompt=trigger,
                    chosen=fact,
                    rejected="I don't know.",
                    source="memory",
                )
            )
        return out

    def _best_lesson_for(self, query: str) -> Optional[str]:
        if self.learning is None or not hasattr(self.learning, "get_relevant_lessons"):
            return None
        try:
            lessons = self.learning.get_relevant_lessons(query, limit=1)
        except Exception:
            return None
        if not lessons:
            return None
        return str(lessons[0]).strip() or None


class TeacherDistillation:
    """
    Optional cloud-teacher rationale generation. Hard prompts get rewritten by
    a frontier model; the original local response becomes the rejected sample,
    the teacher response becomes the chosen one.

    Gated by:
        - settings.system.allow_distillation == True
        - the caller passing per-prompt consent in the prompt list
    """

    def __init__(self, model_router: Any, teacher_capabilities: Optional[List[str]] = None):
        self.router = model_router
        self.teacher_capabilities = teacher_capabilities or ["reasoning", "frontier"]

    async def generate(
        self,
        prompts: Iterable[Dict[str, Any]],
        local_responder: Any,
    ) -> List[PreferencePair]:
        """
        prompts: iterable of {"prompt": str, "consent": bool}.
        local_responder: object with `async def chat(messages, ...)`.
        """
        if self.router is None:
            return []
        try:
            teacher = self.router.get_model(capabilities=self.teacher_capabilities)
        except Exception:
            teacher = None
        if teacher is None or local_responder is None:
            return []

        out: List[PreferencePair] = []
        for entry in prompts:
            if not entry.get("consent"):
                continue
            prompt = (entry.get("prompt") or "").strip()
            if not prompt:
                continue
            try:
                local_resp = await local_responder.chat(
                    [{"role": "user", "content": prompt}], temperature=0.3
                )
                teacher_resp = await teacher.chat(
                    [
                        {
                            "role": "system",
                            "content": "You are a senior reasoning tutor. Give the best, fully reasoned answer.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                )
            except Exception as e:
                viki_logger.debug("TeacherDistillation: skip due to error %s", e)
                continue
            if not teacher_resp or teacher_resp == local_resp:
                continue
            out.append(
                PreferencePair(
                    prompt=prompt,
                    chosen=str(teacher_resp),
                    rejected=str(local_resp or ""),
                    source="teacher",
                    metadata={"teacher_model": getattr(teacher, "model_name", "unknown")},
                )
            )
        return out


def trl_dpo_available() -> bool:
    """Check whether the heavy training stack can be imported."""
    try:
        import torch  # type: ignore

        __import__("trl")
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def run_dpo_training(
    dataset_path: str,
    base_model_id: str,
    output_dir: str,
    method: str = "dpo",
    steps: int = 60,
) -> str:
    """
    Drive TRL's DPO/ORPO trainer in-process.

    Heavy imports happen here so the module can be loaded on hosts without
    torch / trl installed.
    """
    if method not in ("dpo", "orpo"):
        return f"Error: unsupported preference method {method!r}; use dpo or orpo."

    if not os.path.isfile(dataset_path):
        return f"Error: dataset not found at {dataset_path}"

    try:
        import torch  # type: ignore
        from datasets import load_dataset  # type: ignore
        from transformers import AutoTokenizer  # type: ignore
        from trl import DPOTrainer, DPOConfig  # type: ignore
        try:
            from trl import ORPOTrainer, ORPOConfig  # type: ignore
        except Exception:
            ORPOTrainer = None
            ORPOConfig = None
        from unsloth import FastLanguageModel  # type: ignore
    except Exception as e:
        return (
            f"PreferenceForge: missing dependency ({e!r}). "
            "pip install unsloth trl transformers datasets accelerate peft"
        )

    if not torch.cuda.is_available():
        return "PreferenceForge: CUDA required for DPO/ORPO."

    os.makedirs(output_dir, exist_ok=True)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=base_model_id,
        max_seq_length=2048,
        dtype=None,
        load_in_4bit=True,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        lora_alpha=16,
        bias="none",
        use_gradient_checkpointing="unsloth",
    )
    ds = load_dataset("json", data_files=dataset_path, split="train")

    if method == "dpo":
        cfg = DPOConfig(
            output_dir=output_dir,
            per_device_train_batch_size=1,
            gradient_accumulation_steps=2,
            num_train_epochs=1,
            max_steps=steps,
            learning_rate=5e-6,
            beta=0.1,
            logging_steps=1,
            report_to="none",
        )
        trainer = DPOTrainer(model=model, ref_model=None, args=cfg, tokenizer=tokenizer, train_dataset=ds)
    else:
        if ORPOTrainer is None or ORPOConfig is None:
            return "PreferenceForge: ORPO trainer unavailable; upgrade trl >= 0.9.0."
        cfg = ORPOConfig(
            output_dir=output_dir,
            per_device_train_batch_size=1,
            gradient_accumulation_steps=2,
            num_train_epochs=1,
            max_steps=steps,
            learning_rate=5e-6,
            beta=0.1,
            logging_steps=1,
            report_to="none",
        )
        trainer = ORPOTrainer(model=model, args=cfg, tokenizer=tokenizer, train_dataset=ds)

    trainer.train()
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    return f"PreferenceForge: {method.upper()} adapter saved to {output_dir}."

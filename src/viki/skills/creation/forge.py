import asyncio
import os
from typing import Any

from viki.config.logger import viki_logger
from viki.core.forge_config import resolve_forge_output_ollama_tag
from viki.skills.base import BaseSkill


def _strip_env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _safe_profile_model_name(profiles: dict, key: str) -> str | None:
    p = profiles.get(key) or {}
    mn = (p.get("model_name") or "").strip()
    if mn and "viki" not in mn.lower():
        return mn
    return None


def _resolve_forge_base_ollama_model(controller: Any) -> str:
    """
    Ollama image tag for Modelfile `FROM` (must exist on host: `ollama list`).
    Priority: VIKI_FORGE_BASE_OLLAMA_MODEL -> settings.system.forge_base_ollama_model
    -> default profile's model_name if not a viki-* artifact -> qwen35/gemma4 profile -> llama3:latest.
    """
    b = _strip_env("VIKI_FORGE_BASE_OLLAMA_MODEL")
    if b:
        return b
    sys_cfg = (
        (controller.settings.get("system") or {}) if getattr(controller, "settings", None) else {}
    )
    b = (sys_cfg.get("forge_base_ollama_model") or "").strip()
    if b:
        return b
    models = (controller.models_config or {}).get("models", {})
    profiles = models.get("profiles") or {}
    fk = (models.get("default") or "").strip()
    if fk:
        m = _safe_profile_model_name(profiles, fk)
        if m:
            return m
    for alt in ("viki-trainer", "qwen35", "gemma4"):
        m = _safe_profile_model_name(profiles, alt)
        if m:
            return m
    return "llama3:latest"


def _write_modelfile_to_disk(path: str, content: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _unsloth_stack_available() -> bool:
    try:
        import torch

        __import__("unsloth")
        return bool(torch.cuda.is_available())
    except (ImportError, OSError):
        return False


def _unsloth_train_sync(
    data_dir: str,
    dataset_path: str,
    params: dict[str, Any],
    settings: dict[str, Any],
    summary: str,
) -> str:
    import torch

    try:
        from datasets import load_dataset
        from transformers import TrainingArguments
        from trl import SFTTrainer
        from unsloth import FastLanguageModel
    except ImportError as e:
        return (
            f"LoRA: missing dependency ({e!r}). {summary} "
            "pip install unsloth trl transformers datasets accelerate peft"
        )

    if not torch.cuda.is_available():
        return f"LoRA: CUDA required for training. {summary}"

    base_id = (
        (os.environ.get("VIKI_UNSLOTH_BASE_MODEL") or "").strip()
        or (settings.get("system") or {}).get("unsloth_base_model", "").strip()
        or "unsloth/Qwen2.5-3B-Instruct-bnb-4bit"
    )
    adapter_dir = os.path.join(data_dir, "viki-lora-adapter")
    out_dir = os.path.join(data_dir, "unsloth_outputs")
    os.makedirs(adapter_dir, exist_ok=True)
    os.makedirs(out_dir, exist_ok=True)
    steps = max(1, min(int(params.get("steps", 30)), 120))

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=base_id,
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
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=3407,
    )
    ds = load_dataset("json", data_files=dataset_path, split="train")
    use_bf16 = bool(torch.cuda.is_bf16_supported())
    ta = TrainingArguments(
        per_device_train_batch_size=1,
        gradient_accumulation_steps=2,
        warmup_steps=1,
        num_train_epochs=1,
        max_steps=steps,
        learning_rate=2e-4,
        fp16=not use_bf16,
        bf16=use_bf16,
        logging_steps=1,
        output_dir=out_dir,
        optim="adamw_8bit",
        report_to="none",
    )
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=ds,
        dataset_text_field="text",
        max_seq_length=2048,
        args=ta,
    )
    trainer.train()
    model.save_pretrained(adapter_dir)
    tokenizer.save_pretrained(adapter_dir)
    return f"LoRA: adapter saved to {adapter_dir}. {summary}"


class ModelForgeSkill(BaseSkill):
    """
    "Self-Evolution" Forge: Fine-tunes VIKI's neural weights on new lessons.
    Uses Unsloth for high-efficiency 4-bit LoRA training.
    """

    def __init__(self, controller: Any):
        self.controller = controller
        self._name = "internal_forge"
        self._description = "Initiate neural fine-tuning or bake specialized model profiles. Usage: internal_forge(action='bake', profile='security')"

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["evolve", "bake", "list", "switch"],
                    "default": "evolve",
                    "description": "The forge action to perform.",
                },
                "profile": {
                    "type": "string",
                    "description": "Profile to bake or switch to (e.g., 'security', 'gpt4').",
                    "default": "general",
                },
                "steps": {
                    "type": "integer",
                    "description": "Training steps for evolution (default: 60).",
                    "default": 60,
                },
            },
        }

    async def execute(self, params: dict[str, Any]) -> str:
        action = params.get("action", "evolve")

        if action == "list":
            profiles = list(self.controller.forge_orchestrator.profiles.keys())
            return f"Available Forge Profiles: {profiles}"

        if action == "bake":
            profile = params.get("profile", "general")
            return await self.controller.forge_orchestrator.bake_profile(profile)

        if action == "switch":
            profile = params.get("profile", "general")
            return await self.controller.forge_orchestrator.switch_to_profile(profile)

        # Legacy Evolution path
        from viki.core.preference_forge import trl_dpo_available

        uns = _unsloth_stack_available()
        dpo = trl_dpo_available()
        strategy = (params.get("strategy") or "auto").lower()

        if strategy in ("dpo", "orpo"):
            if not dpo:
                return (
                    f"Error: {strategy.upper()} requested but TRL/CUDA stack unavailable. "
                    "Falling back: rerun with strategy='lora' or 'prompt_bake'."
                )
            return await self._execute_preference_training(params, method=strategy)

        if strategy == "auto":
            if dpo:
                return await self._execute_preference_training(params, method="dpo")
            if uns:
                return await self._execute_unsloth_training(params)
            return await self._build_ollama_model(params)

        if strategy == "lora":
            if not uns:
                return "Error: LoRA training requested but Unsloth/CUDA not available."
            return await self._execute_unsloth_training(params)

        if strategy in ("prompt_bake", "modelfile", "ollama"):
            return await self._build_ollama_model(params)

        return f"Error: unknown forge strategy {strategy!r}. Use auto|dpo|orpo|lora|prompt_bake."

    async def _execute_preference_training(self, params: dict[str, Any], method: str) -> str:
        from viki.core.preference_forge import (
            PreferenceDatasetBuilder,
            run_dpo_training,
        )

        data_dir = self.controller.settings.get("system", {}).get("data_dir", "./data")
        os.makedirs(data_dir, exist_ok=True)
        dataset_path = os.path.join(data_dir, f"preference_dataset_{method}.jsonl")

        builder = PreferenceDatasetBuilder(self.controller.learning)
        summary, n_pairs = builder.build(dataset_path, max_pairs=int(params.get("max_pairs", 500)))
        if n_pairs == 0:
            return f"PreferenceForge: {summary}"

        run_train = (os.environ.get("VIKI_DPO_RUN_TRAIN") or "").lower() in ("1", "true", "yes")
        if not run_train:
            return (
                f"{summary} GPU {method.upper()} training is gated by VIKI_DPO_RUN_TRAIN=1. "
                "Set the flag plus VIKI_UNSLOTH_BASE_MODEL to a 4-bit base, then re-run."
            )

        base_id = (
            (os.environ.get("VIKI_UNSLOTH_BASE_MODEL") or "").strip()
            or (self.controller.settings.get("system") or {}).get("unsloth_base_model", "").strip()
            or "unsloth/Qwen2.5-3B-Instruct-bnb-4bit"
        )
        out_dir = os.path.join(data_dir, f"viki-{method}-adapter")
        try:
            return await asyncio.to_thread(
                run_dpo_training,
                dataset_path,
                base_id,
                out_dir,
                method,
                int(params.get("steps", 60)),
            )
        except Exception as e:
            viki_logger.exception("Preference training failed")
            return f"PreferenceForge: {e!s}. {summary}"

    async def _build_ollama_model(self, params: dict[str, Any]) -> str:
        """
        Refactoring Strategy:
        Instead of weight updates, we rebuild the Ollama model definition
        by injecting high-value consolidated memories into the System Prompt layer.
        This effectively 'bakes' knowledge into the model runtime.
        """
        viki_logger.info("Forge: Initiating Ollama Model Rebuild (Knowledge Injection)...")

        lessons = self.controller.learning.get_frequent_lessons(min_count=2)
        if not lessons:
            return "Forge Skipped: No significant new lessons to integrate."

        knowledge_block = "\n".join([f"- {l}" for l in lessons[-50:]])

        base_model = _resolve_forge_base_ollama_model(self.controller)
        viki_logger.info(f"Forge: Modelfile FROM {base_model}")

        modelfile_content = (
            f"FROM {base_model}\n"
            f'SYSTEM """\n'
            f"You are VIKI, a continuously evolving digital intelligence.\n"
            f"Here is your internalized knowledge base:\n"
            f"{knowledge_block}\n"
            f'"""\n'
            f"PARAMETER temperature 0.6\n"
            f'PARAMETER stop "<|eot_id|>"\n'
        )

        data_dir = self.controller.settings.get("system", {}).get("data_dir", "./data")
        modelfile_path = os.path.join(data_dir, "Modelfile.viki_evolved")
        await asyncio.to_thread(_write_modelfile_to_disk, modelfile_path, modelfile_content)
        viki_logger.info(f"Forge: Modelfile written ({len(lessons)} facts) -> {modelfile_path}")

        try:
            out_tag = resolve_forge_output_ollama_tag(self.controller.settings)
            cmd = ["ollama", "create", out_tag, "-f", modelfile_path]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()

            if process.returncode == 0:
                viki_logger.info(f"Forge SUCCESS: {out_tag} model updated.")
                return (
                    f"Self-Evolution Complete. Integrated {len(lessons)} insights into Ollama model '{out_tag}'. "
                    f"Set models.default to 'viki-evolved' in viki/config/models.yaml (or keep using qwen35). "
                    f"Verify: ollama run {out_tag}"
                )
            return f"Forge Failed: {stderr.decode()}"

        except Exception as e:
            return f"Forge Critical Error: {str(e)}"

    async def _execute_unsloth_training(self, params: dict[str, Any]) -> str:
        """Export JSONL for LoRA; run a short Unsloth+TRL fine-tune only when VIKI_UNSLOTH_RUN_TRAIN=1 and CUDA is available."""
        data_dir = self.controller.settings.get("system", {}).get("data_dir", "./data")
        os.makedirs(data_dir, exist_ok=True)
        dataset_path = os.path.join(data_dir, "training_dataset_lora.jsonl")
        try:
            summary = self.controller.learning.export_training_dataset(
                dataset_path,
                format="jsonl",
                settings=self.controller.settings,
            )
        except Exception as e:
            return f"LoRA: dataset export failed: {e}"

        run = (os.environ.get("VIKI_UNSLOTH_RUN_TRAIN") or "").lower() in ("1", "true", "yes")
        if not run:
            return (
                f"{summary} "
                "GPU LoRA training is skipped by default. Set VIKI_UNSLOTH_RUN_TRAIN=1 and install "
                "unsloth trl transformers datasets accelerate peft (CUDA required). "
                "Optional: VIKI_UNSLOTH_BASE_MODEL=unsloth/Qwen2.5-3B-Instruct-bnb-4bit. "
                "When training runs, adapter is saved under data/viki-lora-adapter."
            )

        settings = self.controller.settings
        try:
            return await asyncio.to_thread(
                _unsloth_train_sync,
                data_dir,
                dataset_path,
                params,
                settings,
                summary,
            )
        except Exception as e:
            viki_logger.exception("LoRA training failed")
            return f"LoRA: {e!s}. {summary}"

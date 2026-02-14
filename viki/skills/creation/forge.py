import os
import json
from typing import Dict, Any, List
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger

# Lazy imports moved inside execute

class ModelForgeSkill(BaseSkill):
    """
    "Self-Evolution" Forge: Fine-tunes VIKI's neural weights on new lessons.
    Uses Unsloth for high-efficiency 4-bit LoRA training.
    """
    def __init__(self, controller):
        self.controller = controller
        self._name = "internal_forge"
        self._description = "Initiate neural fine-tuning (Self-Evolution) on learned lessons. Usage: internal_forge()"

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
                "steps": {
                    "type": "integer",
                    "description": "Training steps (default: 60). Higher = more learning.",
                    "default": 60
                }
            }
        }

    async def execute(self, params: Dict[str, Any]) -> str:
        try:
            import torch
            from unsloth import FastLanguageModel
            from trl import SFTTrainer
            from transformers import TrainingArguments
            from datasets import Dataset
            UNSLOTH_AVAILABLE = True
        except ImportError as e:
            viki_logger.warning(f"Unsloth dependencies missing: {e}")
            UNSLOTH_AVAILABLE = False

        if not UNSLOTH_AVAILABLE:
            return "Error: Unsloth library or dependencies not found in the environment."

        viki_logger.info("Forge: Loading lessons from neural memory for fine-tuning...")
        
        try:
            # Get lessons directly from LearningModule
            lessons = self.controller.learning.get_all_lessons()
            
            if not lessons:
                return "Error: No lessons found in the neural memory to train on."

            viki_logger.info(f"Forge: Preparing {len(lessons)} lessons for Llama-3 training...")

            # 1. Format Data for Llama-3
            formatted_data = []
            for item in lessons:
                # Support both v1 and v2 formats
                trigger = item.get("trigger") or item.get("question")
                fact = item.get("fact") or item.get("answer")
                
                if trigger and fact:
                    text = (
                        f"<|begin_of_text|><|start_header_id|>user<|end_header_id|>\n\n"
                        f"{trigger}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n"
                        f"{fact}<|eot_id|>"
                    )
                    formatted_data.append({"text": text})

            if not formatted_data:
                return "Error: Could not extract valid trigger/fact pairs from lessons."

            dataset = Dataset.from_list(formatted_data)

            # 2. Load Model in 4-bit
            viki_logger.info("Forge: Initializing Llama-3-8b (4-bit)...")
            model, tokenizer = FastLanguageModel.from_pretrained(
                model_name = "unsloth/llama-3-8b-bnb-4bit",
                max_seq_length = 2048,
                load_in_4bit = True,
            )

            # 3. Setup PEFT/LoRA
            model = FastLanguageModel.get_peft_model(
                model,
                r = 16,
                target_modules = ["q_proj", "k_proj", "v_proj", "o_proj",
                                 "gate_proj", "up_proj", "down_proj",],
                lora_alpha = 16,
                lora_dropout = 0,
                bias = "none",
                use_gradient_checkpointing = "unsloth",
                random_state = 3407,
                use_rslora = False,
                loftq_config = None,
            )

            # 4. Training Arguments
            train_args = TrainingArguments(
                per_device_train_batch_size = 2,
                gradient_accumulation_steps = 4,
                warmup_steps = 5,
                max_steps = params.get('steps', 60),
                learning_rate = 2e-4,
                fp16 = not torch.cuda.is_available() or not torch.cuda.is_bf16_supported(),
                bf16 = torch.cuda.is_available() and torch.cuda.is_bf16_supported(),
                logging_steps = 1,
                optim = "adamw_8bit",
                weight_decay = 0.01,
                lr_scheduler_type = "linear",
                seed = 3407,
                output_dir = "outputs",
            )

            # 5. Execute Training
            viki_logger.info("Forge: Commencing Neural Evolution...")
            trainer = SFTTrainer(
                model = model,
                tokenizer = tokenizer,
                train_dataset = dataset,
                dataset_text_field = "text",
                max_seq_length = 2048,
                dataset_num_proc = 2,
                packing = False,
                args = train_args,
            )

            trainer.train()

            # 6. Save LoRA Adapter
            adapter_path = "models/viki_adapter"
            model.save_pretrained(adapter_path)
            tokenizer.save_pretrained(adapter_path)

            viki_logger.info(f"Forge SUCCESS: Evolution stable. Adapter saved to {adapter_path}")
            return f"Evolution Successful. Neural LoRA weights updated at {adapter_path}. Restart the core to bake changes."

        except Exception as e:
            viki_logger.error(f"Forge FAILED: {e}")
            return f"Evolution Failure: {str(e)}"

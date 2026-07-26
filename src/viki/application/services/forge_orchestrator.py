import asyncio
import os

from viki.config.logger import viki_logger
from viki.domain.entities.forge import ForgeProfile


class ForgeOrchestrator:
    def __init__(self, controller):
        self.controller = controller
        self.profiles: dict[str, ForgeProfile] = {
            "general": ForgeProfile(
                name="general",
                base_model="llama3:latest",
                target_tag="viki-general",
                knowledge_topics=["*"],
            ),
            "security": ForgeProfile(
                name="security",
                base_model="llama3:latest",
                target_tag="viki-security",
                knowledge_topics=["security", "vulnerability", "pentest"],
                system_instruction_override="You are VIKI Security Specialist. Focus on safe, offensive security research.",
            ),
            "coder": ForgeProfile(
                name="coder",
                base_model="qwen2.5-coder:latest",
                target_tag="viki-coder",
                knowledge_topics=["code", "architecture", "refactor"],
                system_instruction_override="You are VIKI Senior Architect. Focus on clean code and design patterns.",
            ),
            "gpt4": ForgeProfile(
                name="gpt4",
                base_model="gpt-4o",
                target_tag="viki-cloud-gpt4",
                is_cloud=True,
                cloud_provider="openai",
            ),
            "claude": ForgeProfile(
                name="claude",
                base_model="claude-3-5-sonnet-20240620",
                target_tag="viki-cloud-claude",
                is_cloud=True,
                cloud_provider="anthropic",
            ),
        }

    async def bake_profile(self, profile_name: str) -> str:
        """Bake a specific model profile using relevant lessons and a dedicated trainer LLM."""
        if profile_name not in self.profiles:
            return f"Error: Profile {profile_name} not found."

        profile = self.profiles[profile_name]
        viki_logger.info(f"Forge: Initiating Synthesis for '{profile_name}'...")

        # 1. Identify the Trainer Model
        trainer = self.controller.model_router.get_model(["training"])

        # 2. Gather relevant lessons
        lessons = self.controller.learning.get_frequent_lessons(min_count=1)
        if not lessons:
            return "Forge: No lessons found. Interaction required to seed knowledge."

        raw_knowledge = "\n".join([f"- {l}" for l in lessons[-50:]])

        # 3. Use Trainer to synthesize knowledge (Scenario 1)
        viki_logger.info(
            f"Forge: Using trainer model '{trainer.model_name}' to synthesize Digital DNA..."
        )
        synthesis_prompt = [
            {
                "role": "system",
                "content": "You are the VIKI Neural Forge. Summarize the following user lessons into a concise, high-density knowledge block for a system prompt. Focus on facts, preferences, and operational patterns.",
            },
            {"role": "user", "content": raw_knowledge},
        ]

        # We use a simple chat call for synthesis
        digital_dna = await trainer.chat(synthesis_prompt)

        # Refined error check: only fallback if it's a connection/API error, not just a response containing "Error"
        is_real_error = any(
            digital_dna.startswith(prefix)
            for prefix in ["Error calling", "Ollama Error:", "Error: Missing"]
        )
        if is_real_error:
            viki_logger.warning(
                f"Forge: Synthesis failed, falling back to raw lessons. Error: {digital_dna}"
            )
            digital_dna = raw_knowledge

        # 4. Build Modelfile (Scenario 2: VIKI as a new AI model)
        system_msg = (
            profile.system_instruction_override
            or "You are VIKI, a sovereign digital intelligence evolved from user interaction."
        )
        modelfile_content = (
            f"FROM {profile.base_model}\n"
            f'SYSTEM """\n'
            f"{system_msg}\n\n"
            f"DIGITAL DNA (SYTHESIZED KNOWLEDGE):\n"
            f"{digital_dna}\n"
            f'"""\n'
        )
        for k, v in profile.parameters.items():
            modelfile_content += f"PARAMETER {k} {v}\n"

        # 3. Save Modelfile for LM Studio
        data_dir = self.controller.settings.get("system", {}).get("data_dir", "./data")
        modelfile_path = os.path.join(data_dir, f"Modelfile.{profile.target_tag}")

        with open(modelfile_path, "w", encoding="utf-8") as f:
            f.write(modelfile_content)

        try:
            # LM Studio doesn't support programmatic model creation from Modelfiles.
            # Save the Modelfile for the user to apply in LM Studio.
            viki_logger.info(
                f"Forge: Modelfile saved for '{profile.target_tag}'. "
                f"User should apply system prompt in LM Studio."
            )
            return (
                f"Forge Success: Profile '{profile.target_tag}' Modelfile saved at {modelfile_path}.\n"
                f"To apply: Open LM Studio -> Load model -> Settings -> System Prompt -> paste from Modelfile."
            )
        except Exception as e:
            return f"Forge Error: {str(e)}"

    async def bake_lora(
        self,
        base_model_hf: str | None = None,
        base_model_tag: str | None = None,
        target_tag: str = "viki-lora",
    ) -> str:
        """Real fine-tuning path: export lessons → LoRA train → Ollama adapter model.

        Unlike ``bake_profile`` (which bakes lessons into a system prompt),
        this trains actual adapter weights on the lessons DB. Requires the
        optional ML stack (torch/transformers/peft/trl/datasets); reports
        clearly when unavailable.
        """
        from viki.core.forge_lora import (
            LoraConfig,
            LoraDatasetExporter,
            LoraTrainer,
            ml_stack_available,
            write_adapter_modelfile,
        )

        data_dir = self.controller.settings.get("system", {}).get("data_dir", "./data")
        forge_cfg = self.controller.settings.get("forge", {}) or {}
        lora_cfg = LoraConfig(
            base_model=base_model_hf or forge_cfg.get("lora_base_model_hf", LoraConfig.base_model),
            output_dir=os.path.join(data_dir, "forge", "lora"),
        )

        # 1. Export dataset from the lessons DB.
        dataset_path = os.path.join(data_dir, "forge", "lora_dataset.jsonl")
        exporter = LoraDatasetExporter(self.controller.learning.conn, lora_cfg)
        n = await asyncio.to_thread(exporter.export, dataset_path)
        if n == 0:
            return "Forge LoRA: No usable lessons found. Interact more to seed knowledge."

        # 2. Train (heavy; runs in a worker thread).
        ok, reason = ml_stack_available()
        if not ok:
            return (
                f"Forge LoRA: dataset with {n} examples exported to {dataset_path}, "
                f"but training is unavailable. {reason}"
            )
        trainer = LoraTrainer(lora_cfg)
        result = await asyncio.to_thread(trainer.train, dataset_path)
        if result.get("status") != "trained":
            return f"Forge LoRA: training failed: {result.get('reason', 'unknown')}"

        # 3. Save adapter Modelfile for LM Studio
        tag = base_model_tag or forge_cfg.get("lora_base_model_tag", "google/gemma-4-e4b")
        modelfile_path = os.path.join(data_dir, f"Modelfile.{target_tag}")
        write_adapter_modelfile(tag, result["adapter_dir"], modelfile_path)
        return (
            f"Forge LoRA Success: trained on {n} lessons "
            f"({result['seconds']}s). Adapter at {result['adapter_dir']}.\n"
            f"Modelfile saved at: {modelfile_path}\n"
            f"To use: Load the base model in LM Studio and apply the adapter."
        )

    async def switch_to_profile(self, profile_name: str) -> str:
        """Switch the controller's active model to a specific profile."""
        if profile_name not in self.profiles:
            return f"Error: Profile {profile_name} not found."

        profile = self.profiles[profile_name]

        if profile.is_cloud:
            # For cloud profiles, we just update the controller's default model router
            # We assume the API keys are in the environment
            viki_logger.info(f"Forge: Switching to Cloud API ({profile.cloud_provider})...")
            # This logic depends on the specific ModelRouter implementation
            # We'll set it as the override model if available
            if hasattr(self.controller, "model_router"):
                # Try to find a matching model in the router
                for _m_name, m_instance in self.controller.model_router.models.items():
                    if profile.base_model in m_instance.model_name:
                        self.controller.model_router.default_model = m_instance
                        return (
                            f"Switched to Cloud Profile: {profile_name} ({m_instance.model_name})"
                        )

            return f"Cloud Profile {profile_name} is configured, but no matching model found in router. Please check models.yaml."
        else:
            # For local profiles, check if the model exists first
            viki_logger.info(f"Forge: Switching to Local Model ({profile.target_tag})...")
            # If it's a baked model, we use the target_tag
            return f"Active profile set to {profile_name}. Please ensure '{profile.target_tag}' is loaded in LM Studio."

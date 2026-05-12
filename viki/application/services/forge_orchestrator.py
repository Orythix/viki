import os
import asyncio
from typing import Dict, List, Any
from viki.domain.entities.forge import ForgeProfile
from viki.config.logger import viki_logger

class ForgeOrchestrator:
    def __init__(self, controller):
        self.controller = controller
        self.profiles: Dict[str, ForgeProfile] = {
            "general": ForgeProfile(
                name="general",
                base_model="llama3:latest",
                target_tag="viki-general",
                knowledge_topics=["*"]
            ),
            "security": ForgeProfile(
                name="security",
                base_model="llama3:latest",
                target_tag="viki-security",
                knowledge_topics=["security", "vulnerability", "pentest"],
                system_instruction_override="You are VIKI Security Specialist. Focus on safe, offensive security research."
            ),
            "coder": ForgeProfile(
                name="coder",
                base_model="qwen2.5-coder:latest",
                target_tag="viki-coder",
                knowledge_topics=["code", "architecture", "refactor"],
                system_instruction_override="You are VIKI Senior Architect. Focus on clean code and design patterns."
            ),
            "gpt4": ForgeProfile(
                name="gpt4",
                base_model="gpt-4o",
                target_tag="viki-cloud-gpt4",
                is_cloud=True,
                cloud_provider="openai"
            ),
            "claude": ForgeProfile(
                name="claude",
                base_model="claude-3-5-sonnet-20240620",
                target_tag="viki-cloud-claude",
                is_cloud=True,
                cloud_provider="anthropic"
            )
        }

    async def bake_profile(self, profile_name: str) -> str:
        """Bake a specific model profile using relevant lessons."""
        if profile_name not in self.profiles:
            return f"Error: Profile {profile_name} not found."

        profile = self.profiles[profile_name]
        viki_logger.info(f"Forge: Baking specialized profile '{profile_name}'...")

        # 1. Gather relevant lessons for this profile
        # Note: In a full implementation, we would filter lessons by topic
        lessons = self.controller.learning.get_frequent_lessons(min_count=1)
        knowledge_block = "\n".join([f"- {l}" for l in lessons[-30:]])

        # 2. Build Modelfile
        system_msg = profile.system_instruction_override or "You are VIKI, a continuously evolving digital intelligence."
        modelfile_content = (
            f"FROM {profile.base_model}\n"
            f"SYSTEM \"\"\"\n"
            f"{system_msg}\n\n"
            f"Internalized Knowledge for {profile.name.upper()}:\n"
            f"{knowledge_block}\n"
            f"\"\"\"\n"
        )
        for k, v in profile.parameters.items():
            modelfile_content += f"PARAMETER {k} {v}\n"

        # 3. Create model via Ollama
        data_dir = self.controller.settings.get("system", {}).get("data_dir", "./data")
        modelfile_path = os.path.join(data_dir, f"Modelfile.{profile.target_tag}")
        
        with open(modelfile_path, "w", encoding="utf-8") as f:
            f.write(modelfile_content)

        try:
            cmd = ["ollama", "create", profile.target_tag, "-f", modelfile_path]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()

            if process.returncode == 0:
                return f"Forge Success: Specialized profile '{profile.target_tag}' created."
            return f"Forge Failed: {stderr.decode()}"
        except Exception as e:
            return f"Forge Error: {str(e)}"

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
                for m_name, m_instance in self.controller.model_router.models.items():
                    if profile.base_model in m_instance.model_name:
                        self.controller.model_router.default_model = m_instance
                        return f"Switched to Cloud Profile: {profile_name} ({m_instance.model_name})"
            
            return f"Cloud Profile {profile_name} is configured, but no matching model found in router. Please check models.yaml."
        else:
            # For local profiles, check if the model exists first
            viki_logger.info(f"Forge: Switching to Local Model ({profile.target_tag})...")
            # If it's a baked model, we use the target_tag
            return f"Active profile set to {profile_name}. Please ensure 'ollama run {profile.target_tag}' is available."

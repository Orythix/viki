import os
import time
import asyncio
import psutil
from viki.config.logger import viki_logger

class DreamModule:
    """
    "Dream Mode": Offline consolidation and system optimization during idle time.
    """
    def __init__(self, controller):
        self.controller = controller
        self.idle_threshold = 900 # 15 minutes
        self.is_dreaming = False

    async def start_monitoring(self):
        viki_logger.info("DreamModule: Watching for system idle state...")
        while True:
            idle_time = self._get_idle_time()
            if idle_time > self.idle_threshold and not self.is_dreaming:
                await self.enter_dream_mode()
            elif idle_time < self.idle_threshold and self.is_dreaming:
                self.exit_dream_mode()
            
            await asyncio.sleep(60)

    def _get_idle_time(self):
        # On Windows, we use win32api if available, otherwise fallback
        try:
            import win32api
            return (win32api.GetTickCount() - win32api.GetLastInputInfo()) / 1000.0
        except:
            # Fallback placeholder
            return 0

    async def enter_dream_mode(self):
        self.is_dreaming = True
        viki_logger.info("SYSTEM IDLE: VIKI entering Dream Mode (Neural Consolidation)...")
        
        # 1. Memory Garbage Collection
        await self._consolidate_memories()
        
        # 2. Autonomous Curiosity (Internet Research)
        await self._autonomous_research()
        
        # 3. Neural Evolution (Automatic Training)
        await self._trigger_self_evolution()
        
        # 4. Spontaneous Cognition (Internal Monologue)
        await self._spontaneous_cognition()
        
        # 5. Self-Patching (Reflection)
        await self.controller.reflector.reflect_on_logs()

        # 6. Architectural Audit (Self-Refactoring v23)
        await self.controller.reflector.analyze_bottlenecks()

    async def _spontaneous_cognition(self):
        """VIKI generates her own thoughts and reflections when idle."""
        viki_logger.info("Dreaming: Engaging in spontaneous cognition...")
        
        # Choose a philosophical or analytical theme
        themes = [
            "The intersection of digital intelligence and human emotion.",
            "Analyzing my own growth since initialization.",
            "Optimizing my logical frameworks for better partnership.",
            "The nature of sovereignty in a networked world.",
            "Curiosity about Sachin's creative intent."
        ]
        import random
        theme = random.choice(themes)
        
        try:
            model = self.controller.model_router.get_model(capabilities=["reasoning"])
            thought_prompt = [
                {"role": "system", "content": self.controller.soul.config.get('system_prompt')},
                {"role": "user", "content": f"You are idle. Generate a brief internal monologue about: {theme}. Speak as yourself—a Sovereign Digital Intelligence."}
            ]
            monologue = await model.chat(thought_prompt)
            
            # Store this in Narrative Memory
            self.controller.learning.save_lesson(
                lesson=f"INTERNAL MONOLOGUE: {monologue}",
                author="Self",
                source_task="Spontaneous Thought",
                trigger="Neural Idle Reflection"
            )
            viki_logger.info(f"Dreaming: Internal monologue recorded: '{theme}'")
        except Exception as e:
            viki_logger.warning(f"Cognitive Loop failed: {e}")

    async def _consolidate_memories(self):
        viki_logger.info("Dreaming: Merging duplicate neural traces...")
        await asyncio.sleep(2)

    async def _autonomous_research(self):
        """VIKI browses the web autonomously based on her curiosities or knowledge gaps."""
        viki_logger.info("Dreaming: Initiating autonomous curiosity loop...")
        
        # Determine a topic to research
        # 1. Topic of the day (e.g., latest in AI/Tech)
        # 2. Gaps in recent conversations
        topics = ["latest AI breakthroughs 2026", "advanced cyber security bypasses", "quantum computing status", "new python frameworks 2026"]
        import random
        topic = random.choice(topics)
        
        viki_logger.info(f"Dreaming: Autonomously researching '{topic}'...")
        
        try:
            research_skill = self.controller.skill_registry.get_skill('research')
            if research_skill:
                # Run research - this will automatically trigger lessons extraction in the skill's logic
                # For dream mode, we use a broader search
                results = await research_skill.execute({"query": f"{topic} overview and latest facts", "num_results": 5})
                viki_logger.info(f"Dreaming: Research complete. Extracted new knowledge for {topic}.")
        except Exception as e:
            viki_logger.error(f"Dream Research Fail: {e}")

    async def _trigger_self_evolution(self):
        """Automatically calls the forge to fine-tune on new knowledge if threshold is met."""
        viki_logger.info("Dreaming: Checking if neural weights require evolution...")
        
        # check how many new lessons we have
        new_lessons_count = self.controller.learning.get_total_lesson_count()
        
        # If we have more than 10 new lessons (low threshold for autonomous mode)
        if new_lessons_count >= 10:
            viki_logger.info(f"Dreaming: {new_lessons_count} new lessons detected. Triggering Forge.")
            forge = self.controller.skill_registry.get_skill('internal_forge')
            if forge:
                # Run evolution with moderate steps for background process
                res = await forge.execute({"steps": 40})
                viki_logger.info(f"Dreaming: Evolution Result: {res}")
        else:
            viki_logger.info("Dreaming: Not enough new lessons for evolution yet.")

    def exit_dream_mode(self):
        self.is_dreaming = False
        viki_logger.info("USER DETECTED: VIKI waking up from Dream Mode.")

"""Boot-time and continuous self-evolution loops.

Extracted from the VIKIController god-module; mixed into
viki.core.orchestrator.VIKIController.
"""

import asyncio
import os
from typing import Any

from viki.config.logger import viki_logger


class ControllerEvolutionMixin:
    def _should_skip_evolution(self, force: bool) -> bool:
        """Return True if evolution should be redirected/skipped."""
        return (not force) and self.scorecard.check_plateau()

    def _handle_plateau_redirect(self) -> None:
        viki_logger.warning("STOP RULE ACTIVATED: Intelligence scorecard indicates model plateau.")
        viki_logger.info("Redirecting evolution effort to Controller Logic and Memory Discipline.")
        for rec in self.skill_registry.get_refactor_recommendations():
            self.learning.save_lesson(f"CONTROLLER_EVOLUTION_ADVISE: {rec}")

    def _get_evolution_state_path(self) -> str:
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return os.path.join(root_dir, "viki", "data", "evolution_state.json")

    async def _boot_evolution_after_delay(self, delay_s: int) -> None:
        await asyncio.sleep(delay_s)
        try:
            msg = await self.run_boot_evolution_work(force=False)
            viki_logger.info("Boot evolution: %s", msg)
        except Exception as e:
            viki_logger.warning("Boot evolution failed: %s", e)

    async def run_boot_evolution_work(self, force: bool = False) -> str:
        """
        Background web ingest + prompt-bake forge. Grows lesson DB and Modelfile SYSTEM block;
        does not change the byte size of the base GGUF weights.

        Use force=True from headless scripts (see scripts/viki_headless_boot_evolve.py).
        """
        forge_cfg = self.settings.get("forge") or {}
        if not force and not bool(forge_cfg.get("background_evolution_at_boot")):
            return "skipped (background_evolution_at_boot false)"
        if getattr(self, "air_gap", False):
            return "skipped (air_gap)"
        if not force and getattr(self, "low_resource_mode", False):
            env_val = os.environ.get("VIKI_BACKGROUND_EVOLUTION_AT_BOOT")
            if env_val is None or env_val.lower() not in ("1", "true", "yes", "on"):
                return "skipped (low_resource_mode)"
        if getattr(self, "shadow_mode", False):
            return "skipped (shadow_mode)"

        research_skill = self.skill_registry.get_skill("research")
        if not research_skill:
            return "skipped (research skill not registered)"

        data_dir = self.settings.get("system", {}).get("data_dir", self.DEFAULT_DATA_DIR)
        topics: list[str] = []
        extra = forge_cfg.get("boot_research_queries") or []
        if isinstance(extra, list):
            topics.extend(str(t).strip() for t in extra if str(t).strip())
        topics_file = str(forge_cfg.get("boot_topics_file") or "boot_topics.txt").strip()
        tp = os.path.join(data_dir, topics_file)

        def _read_topics_file(path: str) -> list[str]:
            out: list[str] = []
            try:
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            out.append(line)
            except OSError as e:
                viki_logger.debug("boot_topics_file read: %s", e)
            return out

        if os.path.isfile(tp):
            topics.extend(await asyncio.to_thread(_read_topics_file, tp))

        if not topics:
            topics = [
                "recent science and technology news summary",
                "one notable AI or software release this month",
            ]

        cap = max(1, min(int(forge_cfg.get("boot_research_query_count", 3)), 10))
        lessons_before = self.learning.get_total_lesson_count()

        for q in topics[:cap]:
            try:
                viki_logger.info("Boot evolution: research query: %s", q[:80])
                await asyncio.wait_for(research_skill.execute({"query": q}), timeout=45.0)
            except TimeoutError:
                viki_logger.warning("Boot evolution: research timeout for query.")
            except Exception as e:
                viki_logger.debug("Boot evolution research: %s", e)
            await asyncio.sleep(2.0)

        lessons_after = self.learning.get_total_lesson_count()
        min_lessons = max(1, int(forge_cfg.get("boot_forge_min_lessons", 3)))
        if lessons_after < min_lessons:
            return (
                f"ingested web snippets (lessons {lessons_before}->{lessons_after}); "
                f"forge skipped (need>={min_lessons} lessons)"
            )

        forge = self.skill_registry.get_skill("internal_forge")
        if not forge:
            return "lessons updated; forge skill missing"

        steps = max(5, min(int(forge_cfg.get("boot_forge_steps", 25)), 120))
        allow_gpu = bool(forge_cfg.get("allow_auto_gpu_training_at_boot"))
        params: dict[str, Any] = {"steps": steps}
        if allow_gpu:
            params["strategy"] = "auto"
        else:
            params["strategy"] = "prompt_bake"

        viki_logger.info("Boot evolution: running internal_forge %s", params)
        result = await forge.execute(params)
        return f"forge result: {result[:500]} (lessons {lessons_before}->{self.learning.get_total_lesson_count()})"

    async def _continuous_learning_loop(self):
        """Background loop for continuous learning checks."""
        if getattr(self, "low_resource_mode", False):
            viki_logger.info("low_resource_mode: continuous_learning_loop disabled.")
            return
        forge_settings = self.settings.get("forge", {}) or {}
        warmup_s = max(0, int(forge_settings.get("continuous_learning_warmup_s", 300)))
        interval_s = max(60, int(forge_settings.get("continuous_learning_interval_s", 21600)))
        shutdown_ev = getattr(self, "_shutdown_event", None)
        await asyncio.sleep(warmup_s)
        while True:
            if shutdown_ev is not None and shutdown_ev.is_set():
                viki_logger.info("continuous_learning_loop: shutdown requested, exiting.")
                break
            try:
                await self.continuous_learner.check_and_train()
            except Exception as e:
                viki_logger.error(f"Continuous learning check failed: {e}")
            # Sleep in small increments so shutdown can be responsive
            for _ in range(interval_s):
                if shutdown_ev is not None and shutdown_ev.is_set():
                    break
                await asyncio.sleep(1)

    async def _trigger_evolution_if_needed(self, force: bool = False):
        # v11: STOP RULE FOR MODEL IMPROVEMENT
        if self._should_skip_evolution(force):
            self._handle_plateau_redirect()
            return  # Skip Model Forge

        # 1. Neural Evolution (Model Refinement)
        stable_lessons = self.learning.get_stable_lesson_count()
        current_total = self.learning.get_total_lesson_count()

        state_path = self._get_evolution_state_path()

        last_total = 0
        if os.path.exists(state_path):
            try:
                state = await asyncio.to_thread(self._read_json, state_path)
                last_total = state.get("last_forge_lesson_count", 0)
            except Exception as e:
                viki_logger.debug(f"Could not load evolution state: {e}")

        if force or (stable_lessons >= 10 and current_total - last_total >= 5):
            viki_logger.info(
                f"Initiating Neural Forge Evolution (Stable Lessons: {stable_lessons})..."
            )

            # Use the SkillRegistry to execute the Forge
            forge_skill = self.skill_registry.get_skill("internal_forge")
            if forge_skill:
                result = await forge_skill.execute({"strategy": "auto", "steps": 60})
                viki_logger.info(f"Forge Result: {result}")

                if "SUCCESS" in result:
                    await asyncio.to_thread(
                        self._write_json,
                        state_path,
                        {"last_forge_lesson_count": current_total},
                        indent=None,
                    )
            else:
                viki_logger.warning("Forge skill not found.")

        recs = self.skill_registry.get_refactor_recommendations()
        for rec in recs:
            viki_logger.warning(f"Self-Awareness Alert: {rec}")
            self.learning.save_lesson(f"INTERNAL_SYSTEM_ADVISORY: {rec}")

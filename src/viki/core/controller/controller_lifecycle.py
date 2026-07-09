import asyncio
import os
import time
from typing import Any

from viki.config.logger import viki_logger


class LifecycleMixin:
    DEFAULT_DATA_DIR = "./data"
    DEFAULT_WORKSPACE_DIR = "."
    CONFIRM_TOKEN = "/confirm"
    REJECT_TOKEN = "/reject"

    def _on_config_file_changed(self, path: str) -> None:
        try:
            fresh = self._load_yaml(path)
            if not fresh:
                return
            if "settings.yaml" in path or path.endswith("settings.yaml"):
                self.settings.update(fresh)
                self._apply_system_overrides(self.settings.setdefault("system", {}), None)
                self._resolve_models_config()
                viki_logger.info("Config hot-reload: settings.yaml applied.")
            elif "models.yaml" in path or path.endswith("models.yaml"):
                self.models_config = fresh
                if hasattr(self, "model_router") and self.model_router is not None:
                    self.model_router._load_config(self.models_config_path)
                viki_logger.info("Config hot-reload: models.yaml applied.")
        except Exception as e:
            viki_logger.warning("Config hot-reload failed for %s: %s", path, e)

    async def _startup_pulse(self):
        await asyncio.sleep(5)
        if getattr(self, "low_resource_mode", False):
            viki_logger.info(
                "STARTUP PULSE: low_resource_mode ON — skipping autonomous startup pulse."
            )
            return

        viki_logger.info("VIKIController Initialized: Sovereign Intelligence Orchestrator (v8.1.0)")
        self.telemetry.record("system", "startup", {"version": "8.1.0", "mode": "sovereign"})

        active_mission = self.world.get_active_mission()
        if active_mission:
            viki_logger.info(
                f"RESUME ADVISORY: Detected active mission: {active_mission['goal'][:50]}..."
            )
            viki_logger.info(f"Phase: {active_mission['phase']}. Use '/resume' to continue.")

        viki_logger.info("STARTUP PULSE: Initiating autonomous knowledge sync...")

        if not self.air_gap and self.settings.get("system", {}).get("startup_research", False):
            try:
                research_skill = self.skill_registry.get_skill("research")
                if research_skill:
                    viki_logger.info("Startup: Checking web for latest digital trends...")
                    await research_skill.execute(
                        {"query": "latest tech and ai news today", "num_results": 2}
                    )
            except Exception as e:
                viki_logger.debug(f"Startup research pulse failed: {e}")

        forge_cfg = self.settings.get("forge") or {}
        defer_boot_evolution = bool(forge_cfg.get("background_evolution_at_boot"))
        new_lessons = self.learning.get_total_lesson_count()
        if not defer_boot_evolution and new_lessons >= 5:
            viki_logger.info(
                f"Startup: {new_lessons} lessons found. Triggering neural optimization."
            )
            forge = self.skill_registry.get_skill("internal_forge")
            if forge:
                await forge.execute({"steps": 20})
        elif defer_boot_evolution:
            delay_s = max(0, int(forge_cfg.get("boot_evolution_delay_s", 180)))
            viki_logger.info(
                "Startup: background_evolution_at_boot enabled — deferring ingest+forge by %ss.",
                delay_s,
            )
            self._create_tracked_task(self._boot_evolution_after_delay(delay_s), "boot_evolution")

        workspace_dir = self.settings.get("system", {}).get(
            "workspace_dir", self.DEFAULT_WORKSPACE_DIR
        )
        if os.path.exists(workspace_dir):
            viki_logger.info(f"Startup: Initiating autonomous world mapping for {workspace_dir}...")
            self.world.analyze_workspace(workspace_dir)
            self.world.scan_codebase(workspace_dir)

        if not self.air_gap:
            self._create_tracked_task(self.mission_control.start_loop(), "mission_control")

        self._create_tracked_task(self._continuous_learning_loop(), "continuous_learning")

    async def _boot_evolution_after_delay(self, delay_s: int) -> None:
        await asyncio.sleep(delay_s)
        try:
            msg = await self.run_boot_evolution_work(force=False)
            viki_logger.info("Boot evolution: %s", msg)
        except Exception as e:
            viki_logger.warning("Boot evolution failed: %s", e)

    async def run_boot_evolution_work(self, force: bool = False) -> str:
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

    async def _prewarm_default_model(self):
        try:
            await asyncio.sleep(1.5)
            if not self.model_router:
                return
            try:
                model = self.model_router.get_model(["chatter"])
            except Exception as e:
                viki_logger.debug(f"Prewarm: model_router.get_model failed: {e}")
                return
            if model is None:
                return
            chat_fn = getattr(model, "chat", None)
            if chat_fn is None:
                return
            t0 = time.time()
            try:
                if asyncio.iscoroutinefunction(chat_fn):
                    try:
                        await chat_fn([{"role": "user", "content": "."}])
                    except TypeError:
                        await chat_fn([{"role": "user", "content": "."}], 0.0)
                else:
                    chat_fn([{"role": "user", "content": "."}])
            except Exception as e:
                viki_logger.debug(f"Prewarm chat failed (non-fatal): {e}")
                return
            elapsed = time.time() - t0
            viki_logger.info(
                f"Prewarm: default model '{getattr(model, 'model_name', '?')}' loaded in {elapsed:.1f}s."
            )
        except Exception as e:
            viki_logger.debug(f"Prewarm task swallowed: {e}")

    def _create_tracked_task(self, coro, name: str = "unnamed"):
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        task.add_done_callback(lambda t: self._handle_task_exception(t, name))
        viki_logger.debug(f"Created tracked background task: {name}")
        return task

    def _handle_task_exception(self, task: asyncio.Task, name: str):
        try:
            task.result()
        except asyncio.CancelledError:
            viki_logger.debug(f"Background task '{name}' was cancelled")
        except Exception as e:
            viki_logger.error(f"Background task '{name}' failed with exception: {e}", exc_info=True)

    async def _continuous_learning_loop(self):
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
            for _ in range(interval_s):
                if shutdown_ev is not None and shutdown_ev.is_set():
                    break
                await asyncio.sleep(1)

    async def resume_mission(self, on_event=None) -> str:
        mission = self.world.get_active_mission()
        if not mission:
            return "No active mission found to resume."

        goal = mission["goal"]
        viki_logger.info(f"Resuming mission: {goal[:50]}...")

        workflow = self.skill_registry.get_skill("coding_workflow")
        if not workflow:
            return "CodingWorkflowSkill not found. Cannot resume mission."

        return await workflow.execute({"action": "resume"})

    def _init_db(self):
        system = self.settings.get("system", {})
        data_dir = system.get("data_dir", self.DEFAULT_DATA_DIR)
        os.makedirs(data_dir, exist_ok=True)
        workspace_dir = system.get("workspace_dir", self.DEFAULT_WORKSPACE_DIR)
        os.makedirs(workspace_dir, exist_ok=True)

    def _should_skip_evolution(self, force: bool) -> bool:
        return (not force) and self.scorecard.check_plateau()

    def _handle_plateau_redirect(self) -> None:
        viki_logger.warning("STOP RULE ACTIVATED: Intelligence scorecard indicates model plateau.")
        viki_logger.info("Redirecting evolution effort to Controller Logic and Memory Discipline.")
        for rec in self.skill_registry.get_refactor_recommendations():
            self.learning.save_lesson(f"CONTROLLER_EVOLUTION_ADVISE: {rec}")

    def _get_evolution_state_path(self) -> str:
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return os.path.join(root_dir, "viki", "data", "evolution_state.json")

    async def shutdown(self):
        if getattr(self, "_shutting_down", False):
            return
        self._shutting_down = True
        viki_logger.info("Shutting down...")

        if getattr(self, "config_watcher", None) is not None:
            self.config_watcher.stop()

        mcp_client = getattr(self, "mcp_client", None)
        if mcp_client is not None:
            try:
                await mcp_client.disconnect_all()
            except Exception as e:
                viki_logger.debug("MCP disconnect failed: %s", e)

        try:
            self.evolution.flush()
        except Exception as e:
            viki_logger.debug(f"Evolution flush on shutdown: {e}")

        try:
            from viki.core.utils.http_session import close_session

            await close_session()
        except Exception as e:
            viki_logger.debug("HTTP session close failed: %s", e)

        if getattr(self, "_shutdown_event", None) is not None:
            self._shutdown_event.set()

        if self._background_tasks:
            viki_logger.info(f"Cancelling {len(self._background_tasks)} background tasks...")
            for task in self._background_tasks:
                task.cancel()
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
            viki_logger.info("All background tasks cancelled")

        try:
            if len(self.memory.working.get_trace()) > 4:
                viki_logger.info("Synthesizing session narrative...")
                context = self.memory.working.get_trace()
                user_msg_count = sum(1 for m in context if m["role"] == "user")
                summary = f"Had a session with Orythix001 involving {user_msg_count} exchanges. "
                if any(
                    m["role"] == "assistant" and "error" in m["content"].lower() for m in context
                ):
                    summary += "We encountered some technical hurdles but optimized through them."
                else:
                    summary += (
                        "The synchronization was high and we achieved the objectives smoothly."
                    )

                self.learning.save_narrative(
                    summary, significance=0.7, mood=str(self.bio.get_state())
                )

                viki_logger.info("Analyzing session for knowledge extraction...")
                model = self.model_router.get_model(capabilities=["reasoning"])
                facts = await self.learning.analyze_session(model, context, summary)
                if facts:
                    viki_logger.info(f"Session analysis extracted {len(facts)} facts")
                else:
                    viki_logger.info("Session analysis complete — no new lessons extracted.")
        except Exception as e:
            viki_logger.error(f"Narrative synthesis failed: {e}")

        self.wellness.stop()
        self.learning.prune_old_lessons()
        if hasattr(self.learning, "close"):
            self.learning.close()
        if hasattr(self.memory, "close"):
            self.memory.close()
        if hasattr(self, "history") and hasattr(self.history, "close"):
            self.history.close()
        if hasattr(self.scorecard, "flush"):
            self.scorecard.flush()
        self._closed = True

    def close(self):
        if getattr(self, "_closed", False):
            return
        self._closed = True

        try:
            if hasattr(self, "learning") and hasattr(self.learning, "close"):
                self.learning.close()
        except Exception as e:
            viki_logger.debug(f"Controller close: learning close failed: {e}")

        try:
            if hasattr(self, "memory") and hasattr(self.memory, "close"):
                self.memory.close()
        except Exception as e:
            viki_logger.debug(f"Controller close: memory close failed: {e}")

        try:
            if hasattr(self, "history") and hasattr(self.history, "close"):
                self.history.close()
        except Exception as e:
            viki_logger.debug(f"Controller close: history close failed: {e}")

        try:
            if hasattr(self, "telemetry") and hasattr(self.telemetry, "close"):
                self.telemetry.close()
        except Exception as e:
            viki_logger.debug(f"Controller close: telemetry close failed: {e}")

        try:
            if hasattr(self, "scorecard") and hasattr(self.scorecard, "flush"):
                self.scorecard.flush()
        except Exception:
            viki_logger.warning("failed to flush scorecard on close")

        try:
            from viki.core.telemetry_service import close_persistent_traces

            close_persistent_traces()
        except Exception:
            viki_logger.warning("failed to close persistent traces")

    def __del__(self):
        try:
            self.close()
        except Exception:
            viki_logger.warning("error during controller teardown in __del__")

"""Startup pulse, background task tracking, and shutdown.

Extracted from the VIKIController god-module; mixed into
viki.core.orchestrator.VIKIController.
"""

import asyncio
import os
import time

from viki.config.logger import viki_logger
from viki.core.telemetry_service import close_persistent_traces


class ControllerLifecycleMixin:
    def _on_config_file_changed(self, path: str) -> None:
        """Callback invoked by ConfigWatcher when a tracked YAML changes."""
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
        """Autonomous startup sequence: Connect, Research, Evolve.

        Heavy steps (research pulse, evolution pulse, workspace scan,
        mission control, continuous learning) all check
        `low_resource_mode` and short-circuit when it is on, so VIKI
        boots cleanly on machines with little RAM / IO budget.
        """
        await asyncio.sleep(5)  # Give other services time to start
        if getattr(self, "low_resource_mode", False):
            viki_logger.info(
                "STARTUP PULSE: low_resource_mode ON — skipping autonomous startup pulse."
            )
            return

        viki_logger.info("VIKIController Initialized: Sovereign Intelligence Orchestrator (v8.1.0)")
        self.telemetry.record("system", "startup", {"version": "8.1.0", "mode": "sovereign"})

        # v27: Check for active missions from WorldModel
        active_mission = self.world.get_active_mission()
        if active_mission:
            viki_logger.info(
                f"RESUME ADVISORY: Detected active mission: {active_mission['goal'][:50]}..."
            )
            viki_logger.info(f"Phase: {active_mission['phase']}. Use '/resume' to continue.")

        viki_logger.info("STARTUP PULSE: Initiating autonomous knowledge sync...")

        # 1. Quick Research Pulse (optional; disable with system.startup_research: false to speed first request)
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

        # 2. Check for pending evolution (defer if background boot evolution will run later)
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

        # 3. Autonomous World Discovery (v22) — gated to skip on low-resource hosts.
        workspace_dir = self.settings.get("system", {}).get(
            "workspace_dir", self.DEFAULT_WORKSPACE_DIR
        )
        if os.path.exists(workspace_dir):
            viki_logger.info(f"Startup: Initiating autonomous world mapping for {workspace_dir}...")
            self.world.analyze_workspace(workspace_dir)
            self.world.scan_codebase(workspace_dir)

        # 4. Engage Mission Control
        if not self.air_gap:
            self._create_tracked_task(self.mission_control.start_loop(), "mission_control")

        # 5. Start Continuous Learning Monitor (checks periodically for training)
        self._create_tracked_task(self._continuous_learning_loop(), "continuous_learning")

    async def _prewarm_default_model(self):
        """
        Fire a tiny 1-token ping at the default chat model so Ollama loads it
        into memory before the user's first real prompt. Cuts ~5–15 s off
        the cold first-reply on a 4 GB / 4-core box.
        """
        try:
            await asyncio.sleep(1.5)  # let boot settle / MCP attach finish
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
                        # Some chat() signatures take temperature as positional.
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
        """Create a background task with proper tracking and error handling."""
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        task.add_done_callback(lambda t: self._handle_task_exception(t, name))
        viki_logger.debug(f"Created tracked background task: {name}")
        return task

    def _handle_task_exception(self, task: asyncio.Task, name: str):
        """Handle exceptions from background tasks."""
        try:
            task.result()
        except asyncio.CancelledError:
            viki_logger.debug(f"Background task '{name}' was cancelled")
        except Exception as e:
            viki_logger.error(f"Background task '{name}' failed with exception: {e}", exc_info=True)

    async def shutdown(self):
        if getattr(self, "_shutting_down", False):
            return
        self._shutting_down = True
        viki_logger.info("Shutting down...")

        if getattr(self, "config_watcher", None) is not None:
            self.config_watcher.stop()

        if getattr(self, "mcp_client", None) is not None:
            try:
                await self.mcp_client.disconnect_all()
            except Exception as e:
                viki_logger.debug("MCP disconnect failed: %s", e)

        try:
            self.evolution.flush()
        except Exception as e:
            viki_logger.debug(f"Evolution flush on shutdown: {e}")

        # Close shared HTTP session
        try:
            from viki.core.utils.http_session import close_session

            await close_session()
        except Exception as e:
            viki_logger.debug("HTTP session close failed: %s", e)

        # Signal background loops to exit cleanly
        if getattr(self, "_shutdown_event", None) is not None:
            self._shutdown_event.set()

        # Cancel all background tasks
        if self._background_tasks:
            viki_logger.info(f"Cancelling {len(self._background_tasks)} background tasks...")
            for task in self._background_tasks:
                task.cancel()
            # Wait for all tasks to complete cancellation
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
            viki_logger.info("All background tasks cancelled")

        # v12: Session Narrative Synthesis
        try:
            if len(self.memory.working.get_trace()) > 4:  # Only record meaningful sessions
                viki_logger.info("Synthesizing session narrative...")
                context = self.memory.working.get_trace()
                # Create a simple summary of the interaction
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

                # Extract structured facts from session
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
        # v25: Persistence cleanup
        if hasattr(self.learning, "close"):
            self.learning.close()
        if hasattr(self.memory, "close"):
            self.memory.close()
        if hasattr(self, "history") and hasattr(self.history, "close"):
            self.history.close()
        if hasattr(self.scorecard, "flush"):
            self.scorecard.flush()
        # Mark closed so __del__ → close() won't double-clean and interfere
        # with other orchestrators sharing the same database path.
        self._closed = True

    def close(self):
        """Best-effort synchronous close to prevent SQLite file locks in tests.

        Some unit tests may not fully await `shutdown()`, so we also release persistence
        resources here as a safety net (idempotent).
        """
        if getattr(self, "_closed", False):
            return
        self._closed = True

        # Persistence layers
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

        # Flush any debounced state that's safe to flush without async
        try:
            if hasattr(self, "scorecard") and hasattr(self.scorecard, "flush"):
                self.scorecard.flush()
        except Exception:
            pass

        # Phase 6/7: Persistent Traces
        try:
            close_persistent_traces()
        except Exception:
            pass

    def __del__(self):
        # __del__ must never raise.
        try:
            self.close()
        except Exception:
            pass

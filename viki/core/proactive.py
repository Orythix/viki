import os
import time
import asyncio
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from viki.config.logger import viki_logger

class ProactiveHandler(FileSystemEventHandler):
    def __init__(self, controller, loop):
        self.controller = controller
        self.loop = loop

    def on_created(self, event):
        if not event.is_directory:
            filename = os.path.basename(event.src_path)
            viki_logger.info(f"Proactive: Detected new file '{filename}'")
            
            # Trigger VIKI processing for the file
            # We must use run_coroutine_threadsafe because watchdog runs in its own thread
            instruction = f"I detected a new file: {event.src_path}. Please analyze it and tell me what it is."
            asyncio.run_coroutine_threadsafe(
                self.controller.process_request(instruction),
                self.loop
            )

class WellnessPulse:
    """
    Proactive "Wellness Pulse".
    Periodically checks if the user needs anything via Nexus channels.
    """
    def __init__(self, controller):
        self.controller = controller
        self.is_running = False
        self.disabled = False
        self.snoozed_until = 0
        self.dismissed_patterns = set()

    def _should_trigger(self) -> bool:
        """Decide whether we should run a proactive check now."""
        if not self.is_running or self.disabled:
            return False

        if time.time() < self.snoozed_until:
            return False

        last_active = getattr(self.controller, "last_interaction_time", time.time())
        idle_time = time.time() - last_active
        return idle_time >= 7200  # 2 hours

    def _get_suggestions(self) -> list:
        """Compute currently suggested patterns (un-dismissed only)."""
        frequent = self.controller.learning.get_frequent_lessons(3)
        return [l for l in frequent if l not in self.dismissed_patterns]

    async def _send_nexus_prompt(self, best_suggestion: str, msg: str) -> None:
        """Send the proactive prompt to the Nexus if available."""
        if not hasattr(self.controller, "nexus"):
            self.dismissed_patterns.add(best_suggestion)
            return

        async def proactive_callback(response):
            # In proactive mode, we just log the response or handle it silently.
            viki_logger.info(f"WellnessPulse Callback: {response}")
            await asyncio.sleep(0)  # keep callback async without changing behavior

        await self.controller.nexus.ingest(
            source="System",
            user_id="WellnessPulse",
            text=msg,
            callback=proactive_callback,
            priority=30,  # Low priority
        )
        self.dismissed_patterns.add(best_suggestion)

    async def start(self):
        self.is_running = True
        viki_logger.info("WellnessPulse: Awareness layer active.")
        
        while self.is_running:
            # Check every 30 minutes
            await asyncio.sleep(1800) 
            if not self._should_trigger():
                continue

            suggestions = self._get_suggestions()
            if not suggestions:
                continue

            best_suggestion = suggestions[0]
            viki_logger.info(f"WellnessPulse: Pattern detected: {best_suggestion}")

            msg = (
                f"I've noticed a pattern: '{best_suggestion}'. "
                "Should I automate this? (/dismiss, /snooze, or /disable)"
            )
            await self._send_nexus_prompt(best_suggestion, msg)

    def snooze(self, hours=4):
        self.snoozed_until = time.time() + (hours * 3600)
        viki_logger.info(f"WellnessPulse: Snoozed for {hours} hours.")

    def disable(self):
        self.disabled = True
        viki_logger.info("WellnessPulse: Proactive awareness disabled.")

    def stop(self):
        self.is_running = False

class WatchdogModule:
    def __init__(self, controller):
        self.controller = controller
        self.observer = Observer()
        self.watch_dir = controller.settings.get('system', {}).get('workspace_dir', './workspace')
        os.makedirs(self.watch_dir, exist_ok=True)

    def start(self, loop):
        handler = ProactiveHandler(self.controller, loop)
        self.observer.schedule(handler, self.watch_dir, recursive=False)
        self.observer.start()
        viki_logger.info(f"Watchdog started on {self.watch_dir}")

    def stop(self):
        self.observer.stop()
        self.observer.join()

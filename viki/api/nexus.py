import asyncio
from typing import Dict, Any, List
from viki.config.logger import viki_logger

class MessagingNexus:
    """
    Unified Messaging Nexus: One True Event Loop logic.
    Aggregates inputs into a single PriorityQueue.
    """
    def __init__(self, controller):
        self.controller = controller
        self.queue = asyncio.PriorityQueue()
        self.active = False
        self.active_tasks = set()

    async def ingest(self, source: str, user_id: str, text: str, callback: Any, priority: int = 20):
        """
        Ingest with priority.
        10 = Urgent (Reflex/Safety)
        20 = Standard (User Input)
        30 = Proactive (Wellness/Analysis)
        """
        viki_logger.info(f"Nexus Ingest: [{source}/{user_id}] (P{priority}) -> {text[:50]}...")
        await self.queue.put((priority, {
            'source': source,
            'user_id': user_id,
            'text': text,
            'callback': callback
        }))

    async def start_processing(self, on_event=None):
        self.active = True
        viki_logger.info("Nexus: Unified Priority Processor ONLINE.")
        
        while self.active:
            try:
                priority, task_data = await self.queue.get()
                t = asyncio.create_task(self._process_task(task_data, on_event=on_event))
                self.active_tasks.add(t)
                t.add_done_callback(self.active_tasks.discard)
                self.queue.task_done()
            except asyncio.CancelledError:
                break

    async def _process_task(self, task: Dict[str, Any], on_event=None):
        task_id = f"{task['source']}/P{task.get('priority', 'na')}"
        try:
            if on_event: on_event("nexus_task", ("add", task_id))
            response = await self.controller.process_request(task['text'], on_event=on_event)
            await task['callback'](response)
        except Exception as e:
            viki_logger.error(f"Nexus Error: {e}")
            await task['callback'](f"Internal error: {e}")
        finally:
            if on_event: on_event("nexus_task", ("remove", task_id))

    def stop(self):
        self.active = False
        for t in self.active_tasks:
            t.cancel()
        viki_logger.info("Nexus: Task processor stopped and tasks cancelled.")

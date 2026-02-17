"""
Task management: file-based tasks (JSON in data_dir) or Things 3 on macOS via URL scheme.
Config: tasks.provider = file | things3
"""
import os
import json
import asyncio
from typing import Dict, Any
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger


class TasksSkill(BaseSkill):
    def __init__(self, controller=None):
        self._controller = controller

    @property
    def name(self) -> str:
        return "tasks"

    @property
    def description(self) -> str:
        return "Add, list, or complete tasks. Provider: file (default) or things3 on macOS."

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["add", "list", "complete"], "description": "Action."},
                "title": {"type": "string", "description": "Task title."},
                "id": {"type": "string", "description": "Task id for complete."},
            },
            "required": ["action"],
        }

    def _file_path(self) -> str:
        if not self._controller:
            data_dir = os.environ.get("VIKI_DATA_DIR", "./data")
        else:
            data_dir = self._controller.settings.get("system", {}).get("data_dir", "./data")
        return os.path.join(data_dir, "tasks.json")

    def _read_tasks(self) -> list:
        path = self._file_path()
        if not os.path.isfile(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _write_tasks(self, tasks: list) -> None:
        path = self._file_path()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(tasks, f, indent=2)

    async def execute(self, params: Dict[str, Any]) -> str:
        action = (params.get("action") or "list").lower()
        provider = "file"
        if self._controller:
            provider = (self._controller.settings.get("tasks") or {}).get("provider", "file")

        if provider == "things3" and os.name != "nt":
            if action == "add":
                title = params.get("title") or ""
                if not title:
                    return "Provide title for add."
                try:
                    import urllib.parse
                    url = "things:///add?title=" + urllib.parse.quote(title)
                    await asyncio.to_thread(os.system, f'open "{url}"')
                    return f"Added to Things 3: {title}"
                except Exception as e:
                    return f"Things 3 error: {e}"
            if action == "list":
                return "Things 3 list: open Things app for full list (URL scheme does not support list)."
            if action == "complete":
                return "Things 3 complete: use Things app or provide task id if supported."
            return "Unknown action."

        # File provider
        tasks = await asyncio.to_thread(self._read_tasks)
        if action == "add":
            title = params.get("title") or ""
            if not title:
                return "Provide title for add."
            task_id = str(len(tasks) + 1)
            tasks.append({"id": task_id, "title": title, "done": False})
            await asyncio.to_thread(self._write_tasks, tasks)
            return f"Added task: {title} (id={task_id})"
        if action == "list":
            pending = [t for t in tasks if not t.get("done")]
            if not pending:
                return "No pending tasks."
            return "TASKS:\n" + "\n".join([f"- [{t['id']}] {t.get('title', '')}" for t in pending])
        if action == "complete":
            tid = params.get("id")
            if not tid:
                return "Provide id for complete."
            for t in tasks:
                if str(t.get("id")) == str(tid):
                    t["done"] = True
                    await asyncio.to_thread(self._write_tasks, tasks)
                    return f"Completed: {t.get('title', '')}"
            return f"Task id {tid} not found."
        return "Unknown action. Use add, list, complete."
"""
Task scheduler — cron-like recurring missions.

Extends MissionControl with a scheduler that supports:
  - cron expressions (\"0 6 * * *\")
  - simple intervals (every N seconds/minutes/hours)
  - one-shot scheduled tasks
  - per-task token/time budgets
  - hard kill switch (pause all scheduled tasks)
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import auto
from typing import Any

from viki._compat import StrEnum
from viki.config.logger import viki_logger


class ScheduleType(StrEnum):
    INTERVAL = auto()
    CRON = auto()
    ONESHOT = auto()


@dataclass
class ScheduledTask:
    """A task registered with the scheduler."""

    id: str = ""
    name: str = ""
    schedule_type: ScheduleType = ScheduleType.INTERVAL
    # For INTERVAL: seconds between runs
    interval_seconds: int = 0
    # For CRON: standard 5-field cron expression
    cron_expr: str = ""
    # For ONESHOT: unix timestamp to fire
    fire_at: float = 0.0
    # The mission description to create when this task fires
    mission_description: str = ""
    mission_priority: int = 50
    mission_type: str = "maintenance"
    # Budget controls
    max_tokens_per_run: int = 0  # 0 = unlimited
    max_duration_seconds: int = 0  # 0 = unlimited
    # Runtime state
    enabled: bool = True
    last_fired: float = 0.0
    next_fire: float = 0.0
    total_runs: int = 0
    consecutive_failures: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "schedule_type": self.schedule_type,
            "interval_seconds": self.interval_seconds,
            "cron_expr": self.cron_expr,
            "fire_at": self.fire_at,
            "mission_description": self.mission_description,
            "mission_priority": self.mission_priority,
            "mission_type": self.mission_type,
            "max_tokens_per_run": self.max_tokens_per_run,
            "max_duration_seconds": self.max_duration_seconds,
            "enabled": self.enabled,
            "last_fired": self.last_fired,
            "next_fire": self.next_fire,
            "total_runs": self.total_runs,
            "consecutive_failures": self.consecutive_failures,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScheduledTask:
        t = cls()
        for k, v in data.items():
            if hasattr(t, k):
                setattr(t, k, v)
        return t


# Minimal cron parser (supports standard 5-field expressions)
# Field order: minute hour day-of-month month day-of-week


def _parse_cron_field(field: str, min_val: int, max_val: int) -> set[int]:
    """Parse a single cron field (e.g. '*/5', '1,3,5', '*' ) into allowed values."""
    result: set[int] = set()
    field = field.strip()
    if field == "*":
        return set(range(min_val, max_val + 1))

    parts = field.split(",")
    for part in parts:
        part = part.strip()
        if "/" in part:
            base, step_str = part.split("/", 1)
            step = int(step_str)
            base = base.strip()
            if base == "*":
                result.update(range(min_val, max_val + 1, step))
            else:
                start = int(base)
                result.update(range(start, max_val + 1, step))
        elif "-" in part:
            a, b = part.split("-", 1)
            result.update(range(int(a), int(b) + 1))
        else:
            result.add(int(part))
    return {v for v in result if min_val <= v <= max_val}


def _cron_next(cron_expr: str, after: float | None = None) -> float:
    """
    Compute the next datetime matching a 5-field cron expression.

    Fields: minute (0-59), hour (0-23), day-of-month (1-31),
            month (1-12), day-of-week (0-6, 0=Sunday).
    """
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression (expected 5 fields): {cron_expr!r}")

    minute_ok = _parse_cron_field(parts[0], 0, 59)
    hour_ok = _parse_cron_field(parts[1], 0, 23)
    dom_ok = _parse_cron_field(parts[2], 1, 31)
    month_ok = _parse_cron_field(parts[3], 1, 12)
    dow_ok = _parse_cron_field(parts[4], 0, 6)

    now = datetime.fromtimestamp(after or time.time(), tz=timezone.utc)
    # Start searching from the next minute (add 1 minute to avoid returning a time <= after)
    current = now.replace(second=0, microsecond=0) + __import__("datetime").timedelta(minutes=1)

    for _ in range(525600):  # Search up to 1 year ahead
        if current.month not in month_ok:
            current = current.replace(day=1, hour=0, minute=0) + __import__("datetime").timedelta(
                days=32
            )
            current = current.replace(day=1)
            continue
        if current.day not in dom_ok:
            current += __import__("datetime").timedelta(days=1)
            current = current.replace(hour=0, minute=0)
            continue
        if current.weekday() not in dow_ok:
            current += __import__("datetime").timedelta(days=1)
            current = current.replace(hour=0, minute=0)
            continue
        if current.hour not in hour_ok:
            current += __import__("datetime").timedelta(hours=1)
            current = current.replace(minute=0)
            continue
        if current.minute not in minute_ok:
            current += __import__("datetime").timedelta(minutes=1)
            continue
        # All fields match
        return float(current.timestamp())

    return 0.0


class TaskScheduler:
    """
    Cron-like scheduler for recurring missions.

    Attaches to a MissionControl instance and creates missions on schedule.
    Supports pause/resume and persistence.
    """

    def __init__(
        self,
        mission_control: Any,
        persistence_path: str = "",
    ):
        self._mc = mission_control
        self._tasks: dict[str, ScheduledTask] = {}
        self._persistence_path = persistence_path
        self._running = False
        self._paused = False
        self._loop_task: asyncio.Task[Any] | None = None

        if self._persistence_path:
            os.makedirs(os.path.dirname(self._persistence_path) or ".", exist_ok=True)
            self._load()

    # ---- Public API ----

    def add_interval(
        self,
        name: str,
        description: str,
        interval_seconds: int,
        priority: int = 50,
        mission_type: str = "maintenance",
        max_tokens: int = 0,
        max_duration: int = 0,
    ) -> str:
        """Add a task that fires every *interval_seconds*."""
        import uuid

        task = ScheduledTask(
            id=str(uuid.uuid4())[:8],
            name=name,
            schedule_type=ScheduleType.INTERVAL,
            interval_seconds=interval_seconds,
            mission_description=description,
            mission_priority=priority,
            mission_type=mission_type,
            max_tokens_per_run=max_tokens,
            max_duration_seconds=max_duration,
            next_fire=time.time() + interval_seconds,
        )
        self._tasks[task.id] = task
        self._save()
        viki_logger.info(
            "TaskScheduler: added interval task '%s' (every %ds)", name, interval_seconds
        )
        return task.id

    def add_cron(
        self,
        name: str,
        description: str,
        cron_expr: str,
        priority: int = 50,
        mission_type: str = "maintenance",
        max_tokens: int = 0,
        max_duration: int = 0,
    ) -> str:
        """Add a task that fires per a cron expression."""
        import uuid

        next_fire = _cron_next(cron_expr)
        task = ScheduledTask(
            id=str(uuid.uuid4())[:8],
            name=name,
            schedule_type=ScheduleType.CRON,
            cron_expr=cron_expr,
            mission_description=description,
            mission_priority=priority,
            mission_type=mission_type,
            max_tokens_per_run=max_tokens,
            max_duration_seconds=max_duration,
            next_fire=next_fire,
        )
        self._tasks[task.id] = task
        self._save()
        viki_logger.info("TaskScheduler: added cron task '%s' (%s)", name, cron_expr)
        return task.id

    def add_oneshot(
        self,
        name: str,
        description: str,
        fire_at: float,
        priority: int = 50,
        mission_type: str = "maintenance",
    ) -> str:
        """Add a task that fires once at *fire_at*."""
        import uuid

        task = ScheduledTask(
            id=str(uuid.uuid4())[:8],
            name=name,
            schedule_type=ScheduleType.ONESHOT,
            fire_at=fire_at,
            mission_description=description,
            mission_priority=priority,
            mission_type=mission_type,
            next_fire=fire_at,
        )
        self._tasks[task.id] = task
        self._save()
        viki_logger.info("TaskScheduler: added oneshot task '%s' at %s", name, fire_at)
        return task.id

    def remove(self, task_id: str) -> bool:
        """Remove a scheduled task by ID."""
        if task_id in self._tasks:
            del self._tasks[task_id]
            self._save()
            return True
        return False

    def pause(self) -> None:
        """Pause all scheduled execution (hard kill switch)."""
        self._paused = True
        viki_logger.warning("TaskScheduler: PAUSED (all scheduled tasks suspended)")

    def resume(self) -> None:
        """Resume scheduled execution."""
        self._paused = False
        viki_logger.info("TaskScheduler: RESUMED")

    def list_tasks(self) -> list[ScheduledTask]:
        """Return all registered tasks."""
        return list(self._tasks.values())

    def get_task(self, task_id: str) -> ScheduledTask | None:
        return self._tasks.get(task_id)

    # ---- Lifecycle ----

    def start(self) -> None:
        """Start the scheduler background loop."""
        if self._running:
            return
        self._running = True
        self._loop_task = asyncio.create_task(self._run_loop())
        viki_logger.info("TaskScheduler: started (%d tasks)", len(self._tasks))

    async def stop(self) -> None:
        """Stop the scheduler background loop."""
        self._running = False
        if self._loop_task is not None:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None
        viki_logger.info("TaskScheduler: stopped")

    async def _run_loop(self) -> None:
        """Background loop that checks for tasks to fire."""
        while self._running:
            try:
                if not self._paused:
                    now = time.time()
                    for task in list(self._tasks.values()):
                        if not task.enabled:
                            continue
                        if task.next_fire > 0 and now >= task.next_fire:
                            await self._fire_task(task)
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                break
            except Exception as e:
                viki_logger.error("TaskScheduler loop error: %s", e)
                await asyncio.sleep(30)

    async def _fire_task(self, task: ScheduledTask) -> None:
        """Fire a scheduled task by creating a mission."""
        viki_logger.info("TaskScheduler: firing task '%s'", task.name)
        try:
            self._mc.add_mission(
                description=task.mission_description,
                priority=task.mission_priority,
                m_type=task.mission_type,
            )
            task.last_fired = time.time()
            task.total_runs += 1
            task.consecutive_failures = 0

            # Schedule next fire
            if task.schedule_type == ScheduleType.INTERVAL:
                task.next_fire = task.last_fired + task.interval_seconds
            elif task.schedule_type == ScheduleType.CRON:
                task.next_fire = _cron_next(task.cron_expr, after=task.last_fired)
            elif task.schedule_type == ScheduleType.ONESHOT:
                task.enabled = False
                task.next_fire = 0.0

            self._save()
        except Exception as e:
            task.consecutive_failures += 1
            viki_logger.error("TaskScheduler: fire failed for '%s': %s", task.name, e)
            # Disable after 10 consecutive failures
            if task.consecutive_failures >= 10:
                task.enabled = False
                viki_logger.warning(
                    "TaskScheduler: disabled task '%s' (10 consecutive failures)", task.name
                )
            self._save()

    # ---- Persistence ----

    def _save(self) -> None:
        if not self._persistence_path:
            return
        try:
            data = [t.to_dict() for t in self._tasks.values()]
            with open(self._persistence_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            viki_logger.error("TaskScheduler: failed to save: %s", e)

    def _load(self) -> None:
        if not os.path.exists(self._persistence_path):
            return
        try:
            with open(self._persistence_path) as f:
                data = json.load(f)
            for item in data:
                task = ScheduledTask.from_dict(item)
                self._tasks[task.id] = task
            viki_logger.info("TaskScheduler: restored %d tasks", len(self._tasks))
        except Exception as e:
            viki_logger.error("TaskScheduler: failed to load: %s", e)

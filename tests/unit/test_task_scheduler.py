"""Tests for TaskScheduler and cron parser."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from viki.core.task_scheduler import (
    ScheduledTask,
    ScheduleType,
    TaskScheduler,
    _cron_next,
    _parse_cron_field,
)


class TestParseCronField:
    def test_wildcard(self) -> None:
        assert _parse_cron_field("*", 0, 59) == set(range(60))

    def test_step(self) -> None:
        assert _parse_cron_field("*/15", 0, 59) == {0, 15, 30, 45}

    def test_comma_separated(self) -> None:
        assert _parse_cron_field("1,3,5", 0, 59) == {1, 3, 5}

    def test_range(self) -> None:
        assert _parse_cron_field("1-5", 0, 59) == {1, 2, 3, 4, 5}

    def test_out_of_range_clamped(self) -> None:
        assert _parse_cron_field("99", 0, 59) == set()

    def test_step_from_value(self) -> None:
        assert _parse_cron_field("1/10", 0, 59) == {1, 11, 21, 31, 41, 51}

    def test_day_of_week_wildcard(self) -> None:
        assert _parse_cron_field("*", 0, 6) == set(range(7))


class TestCronNext:
    def test_every_minute(self) -> None:
        after = 1_700_000_000.0
        ts = _cron_next("* * * * *", after=after)
        assert ts > after, f"expected {ts} > {after}"

    def test_specific_hour(self) -> None:
        ts = _cron_next("0 6 * * *", after=1_700_000_000)
        import datetime

        dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
        assert dt.hour == 6
        assert dt.minute == 0

    def test_invalid_expression(self) -> None:
        with pytest.raises(ValueError, match="Invalid cron expression"):
            _cron_next("invalid")

    def test_weekday_constraint(self) -> None:
        ts = _cron_next("0 9 * * 1-5", after=1_700_000_000)
        import datetime

        dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
        assert dt.weekday() < 5

    def test_month_constraint(self) -> None:
        ts = _cron_next("0 0 1 1 *", after=1_700_000_000)
        import datetime

        dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
        assert dt.month == 1
        assert dt.day == 1

    def test_next_respects_after(self) -> None:
        after = 1_799_999_000.0
        ts = _cron_next("* * * * *", after=after)
        assert ts > after, f"expected {ts} > {after}"


class TestScheduledTask:
    def test_to_dict_roundtrip(self) -> None:
        task = ScheduledTask(
            id="abc",
            name="test",
            schedule_type=ScheduleType.INTERVAL,
            interval_seconds=3600,
            mission_description="hourly check",
        )
        data = task.to_dict()
        restored = ScheduledTask.from_dict(data)
        assert restored.id == task.id
        assert restored.name == task.name
        assert restored.interval_seconds == 3600

    def test_from_dict_ignores_unknown(self) -> None:
        data = {"id": "x", "name": "y", "unknown": "z"}
        t = ScheduledTask.from_dict(data)
        assert t.id == "x"
        assert not hasattr(t, "unknown")


class TestTaskScheduler:
    @pytest.fixture
    def persistence_path(self, tmp_path: Path) -> str:
        return str(tmp_path / "scheduler_tasks.json")

    @pytest.fixture
    def mission_control(self) -> object:
        class _StubMC:
            def __init__(self) -> None:
                self.missions: list[dict] = []

            def add_mission(self, description: str, priority: int, m_type: str) -> None:
                self.missions.append(
                    {
                        "description": description,
                        "priority": priority,
                        "type": m_type,
                    }
                )

        return _StubMC()

    @pytest.fixture
    def scheduler(self, persistence_path: str, mission_control: object) -> TaskScheduler:
        return TaskScheduler(mission_control, persistence_path=persistence_path)

    def test_add_interval(self, scheduler: TaskScheduler) -> None:
        tid = scheduler.add_interval("hourly", "Hourly maintenance", 3600)
        assert len(tid) == 8
        task = scheduler.get_task(tid)
        assert task is not None
        assert task.schedule_type == ScheduleType.INTERVAL
        assert task.interval_seconds == 3600

    def test_add_cron(self, scheduler: TaskScheduler) -> None:
        tid = scheduler.add_cron("daily", "Daily report", "0 6 * * *")
        task = scheduler.get_task(tid)
        assert task is not None
        assert task.schedule_type == ScheduleType.CRON
        assert task.cron_expr == "0 6 * * *"
        assert task.next_fire > 0

    def test_add_oneshot(self, scheduler: TaskScheduler) -> None:
        future = time.time() + 86400
        tid = scheduler.add_oneshot("deploy", "Deploy release", future)
        task = scheduler.get_task(tid)
        assert task is not None
        assert task.schedule_type == ScheduleType.ONESHOT
        assert task.fire_at == future

    def test_remove_task(self, scheduler: TaskScheduler) -> None:
        tid = scheduler.add_interval("temp", "Temp task", 60)
        assert scheduler.remove(tid) is True
        assert scheduler.get_task(tid) is None

    def test_remove_nonexistent(self, scheduler: TaskScheduler) -> None:
        assert scheduler.remove("nope") is False

    def test_list_tasks(self, scheduler: TaskScheduler) -> None:
        scheduler.add_interval("a", "Task A", 60)
        scheduler.add_interval("b", "Task B", 120)
        assert len(scheduler.list_tasks()) == 2

    def test_pause_resume(self, scheduler: TaskScheduler) -> None:
        assert scheduler._paused is False
        scheduler.pause()
        assert scheduler._paused is True
        scheduler.resume()
        assert scheduler._paused is False

    def test_start_stop(self, scheduler: TaskScheduler) -> None:
        import asyncio

        async def _run() -> None:
            scheduler.start()
            assert scheduler._running is True
            assert scheduler._loop_task is not None
            await scheduler.stop()

        asyncio.run(_run())

    def test_persistence_adds_task(self, scheduler: TaskScheduler, persistence_path: str) -> None:
        scheduler.add_interval("persist", "Persist test", 300)
        with open(persistence_path) as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["name"] == "persist"

    def test_persistence_restores(
        self, scheduler: TaskScheduler, mission_control: object, persistence_path: str
    ) -> None:
        scheduler.add_interval("restore-me", "Will be restored", 600)
        scheduler2 = TaskScheduler(mission_control, persistence_path=persistence_path)
        tasks = scheduler2.list_tasks()
        assert len(tasks) == 1
        assert tasks[0].name == "restore-me"

    def test_oneshot_disabled_after_fire(self, scheduler: TaskScheduler) -> None:
        past = time.time() - 10
        mc = scheduler._mc
        tid = scheduler.add_oneshot("past-event", "Already due", past)
        task = scheduler.get_task(tid)

        # Simulate firing (normally done by _run_loop)
        import asyncio

        asyncio.run(scheduler._fire_task(task))

        assert task.last_fired > 0
        assert task.total_runs == 1
        assert task.enabled is False
        assert task.next_fire == 0.0
        assert len(mc.missions) == 1  # type: ignore[attr-defined]
        assert mc.missions[0]["description"] == "Already due"  # type: ignore[attr-defined]

    def test_consecutive_failures_disables(self, scheduler: TaskScheduler) -> None:
        mc = scheduler._mc

        def _fail(*args: object, **kwargs: object) -> None:
            raise RuntimeError("mission control unavailable")

        mc.add_mission = _fail  # type: ignore[attr-defined]

        tid = scheduler.add_interval("failing", "Will fail", 60)
        task = scheduler.get_task(tid)

        import asyncio

        for _ in range(10):
            asyncio.run(scheduler._fire_task(task))

        assert task.enabled is False
        assert task.consecutive_failures >= 10

"""Tests for background task quiet mode."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


class TestQuietBackground:
    """Test VIKI_QUIET_BACKGROUND env var."""

    def test_quiet_background_disables_dream_monologue(self, monkeypatch):
        """DreamModule._spontaneous_cognition should return early when quiet."""
        monkeypatch.setenv("VIKI_QUIET_BACKGROUND", "true")

        from viki.core.state_consolidation import DreamModule

        controller = MagicMock()
        controller.model_router.get_model = MagicMock()
        controller.learning.save_lesson = MagicMock()

        dream = DreamModule(controller)

        # This should return early without calling model
        import asyncio

        asyncio.run(dream._spontaneous_cognition())

        controller.model_router.get_model.assert_not_called()
        controller.learning.save_lesson.assert_not_called()

    def test_quiet_background_disables_wellness_dream_tasks(self, monkeypatch):
        """_start_background_tasks should skip wellness/dream when quiet."""
        monkeypatch.setenv("VIKI_QUIET_BACKGROUND", "true")

        from viki.cli import _start_background_tasks

        controller = MagicMock()
        controller.low_resource_mode = False
        controller.bio.start = AsyncMock()
        controller.nexus.start_processing = MagicMock()
        controller.wellness.start = MagicMock()
        controller.dream.start_monitoring = MagicMock()
        controller.reflector.reflect_on_logs = MagicMock()
        controller.watchdog.start = MagicMock()
        controller._create_tracked_task = MagicMock()

        interface = MagicMock()
        loop = MagicMock()
        on_event = MagicMock()

        import asyncio

        asyncio.run(_start_background_tasks(controller, on_event, loop, interface))

        # Check that wellness.start was not called as a tracked task
        wellness_calls = [
            c
            for c in controller._create_tracked_task.call_args_list
            if len(c[0]) > 0 and c[0][0] == controller.wellness.start()
        ]
        assert len(wellness_calls) == 0

        dream_calls = [
            c
            for c in controller._create_tracked_task.call_args_list
            if len(c[0]) > 0 and c[0][0] == controller.dream.start_monitoring()
        ]
        assert len(dream_calls) == 0

    def test_low_resource_mode_disables_background_tasks(self, monkeypatch):
        """low_resource_mode should disable wellness/dream tasks."""
        monkeypatch.delenv("VIKI_QUIET_BACKGROUND", raising=False)

        from viki.cli import _start_background_tasks

        controller = MagicMock()
        controller.low_resource_mode = True
        controller.bio.start = AsyncMock()
        controller.nexus.start_processing = MagicMock()
        controller.wellness.start = MagicMock()
        controller.dream.start_monitoring = MagicMock()
        controller.reflector.reflect_on_logs = MagicMock()
        controller.watchdog.start = MagicMock()
        controller._create_tracked_task = MagicMock()

        interface = MagicMock()
        loop = MagicMock()
        on_event = MagicMock()

        import asyncio

        asyncio.run(_start_background_tasks(controller, on_event, loop, interface))

        # Wellness and dream should NOT be started
        wellness_calls = [
            c
            for c in controller._create_tracked_task.call_args_list
            if c[0][0] == controller.wellness.start()
        ]
        assert len(wellness_calls) == 0

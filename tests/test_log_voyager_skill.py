import os
import shutil
import tempfile

import pytest
from viki.skills.builtins.log_voyager_skill import LogVoyagerSkill


class MockTelemetry:
    def get_summary(self):
        return {"total_events": 3, "errors": 2, "warnings": 1, "categories": {"test": 3}}

    def query(self, category=None, limit=20, severity=None):
        return [
            {
                "category": "test",
                "payload": {"message": "DB Locked"},
                "severity": "ERROR",
                "timestamp": 0,
                "event_type": "err",
            },
            {
                "category": "test",
                "payload": {"message": "Router failed"},
                "severity": "ERROR",
                "timestamp": 0,
                "event_type": "err",
            },
        ]


class MockController:
    def __init__(self):
        self.settings = {}
        self.telemetry = MockTelemetry()


@pytest.fixture
def temp_logs(monkeypatch):
    tmp_dir = tempfile.mkdtemp()
    log_dir = os.path.join(tmp_dir, "logs")
    os.makedirs(log_dir)

    # Create mock logs
    viki_log = os.path.join(log_dir, "log")
    with open(viki_log, "w") as f:
        f.write("INFO: System start\nERROR: DB Locked\nWARNING: High latency\n")

    thought_log = os.path.join(log_dir, "thoughts.log")
    with open(thought_log, "w") as f:
        f.write("THOUGHT: Planning route\nERROR: Router failed\n")

    # Mock os.getcwd to return tmp_dir
    monkeypatch.setattr(os, "getcwd", lambda: tmp_dir)

    ctrl = MockController()
    yield ctrl, log_dir
    shutil.rmtree(tmp_dir)


@pytest.mark.asyncio
async def test_log_voyager_scan(temp_logs):
    ctrl, _ = temp_logs
    skill = LogVoyagerSkill(ctrl)

    result = await skill.execute({"action": "scan", "query": "ERROR"})
    assert "DB Locked" in result
    assert "Router failed" in result


@pytest.mark.asyncio
async def test_log_voyager_summarize(temp_logs):
    ctrl, _ = temp_logs
    skill = LogVoyagerSkill(ctrl)

    result = await skill.execute({"action": "summarize"})
    assert "DEGRADED" in result
    assert "Active Errors: 2" in result
    assert "Active Warnings: 1" in result

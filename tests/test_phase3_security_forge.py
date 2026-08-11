"""Unit tests for Phase 3 DockerSandbox and AutoLoraForgeService."""

from __future__ import annotations

import os
import sqlite3

import pytest

from viki.core.forge_lora import AutoLoraForgeService
from viki.skills.sandbox import DockerSandbox


@pytest.mark.asyncio
async def test_docker_sandbox_fallback(tmp_path):
    from viki.skills.sandbox import SandboxConfig

    sandbox = DockerSandbox(config=SandboxConfig(allowed_paths=[str(tmp_path), os.getcwd()]))
    # Force docker_available = False for local fallback test
    sandbox.docker_available = False

    result = await sandbox.run_python("print('sandbox_test_ok')", cwd=str(tmp_path))
    assert result.success
    assert "sandbox_test_ok" in result.output


def test_auto_lora_forge_service_export(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE lessons (
            id TEXT PRIMARY KEY,
            content TEXT,
            text_representation TEXT,
            reliability REAL,
            access_count INT,
            source_task TEXT,
            created_at REAL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO lessons (id, content, text_representation, reliability, access_count, source_task, created_at)
        VALUES ('1', '{"trigger":"test trigger", "fact":"test fact payload text"}', 'test fact payload text', 1.0, 5, 'task', 100.0)
        """
    )
    conn.commit()

    service = AutoLoraForgeService(conn)
    out_jsonl = tmp_path / "auto_dataset.jsonl"

    res = service.check_and_export(jsonl_out_path=str(out_jsonl))
    assert res["status"] == "exported"
    assert res["examples_count"] == 1
    assert os.path.exists(out_jsonl)

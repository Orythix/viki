"""Tests for the Forge LoRA pipeline (dataset export + Modelfile generation)."""

import json
import os
import sqlite3
import time

from viki.core.forge_lora import (
    LoraConfig,
    LoraDatasetExporter,
    LoraTrainer,
    write_adapter_modelfile,
)


def _make_lessons_db(rows):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE lessons (
        id TEXT PRIMARY KEY, content TEXT, text_representation TEXT,
        embedding TEXT, created_at REAL, last_accessed REAL,
        access_count INTEGER DEFAULT 1, author TEXT, source_task TEXT,
        reliability REAL)"""
    )
    for i, (content, text, reliability) in enumerate(rows):
        conn.execute(
            "INSERT INTO lessons (id, content, text_representation, created_at, reliability)"
            " VALUES (?, ?, ?, ?, ?)",
            (f"l{i}", content, text, time.time(), reliability),
        )
    conn.commit()
    return conn


def test_export_structured_lesson(tmp_path):
    conn = _make_lessons_db(
        [
            (
                json.dumps(
                    {"trigger": "What editor does the user prefer?", "fact": "Neovim with LazyVim."}
                ),
                "What editor does the user prefer?: Neovim with LazyVim.",
                1.0,
            )
        ]
    )
    out = str(tmp_path / "ds.jsonl")
    n = LoraDatasetExporter(conn).export(out)
    assert n == 1
    ex = json.loads(open(out).readline())
    roles = [m["role"] for m in ex["messages"]]
    assert roles == ["system", "user", "assistant"]
    assert ex["messages"][1]["content"] == "What editor does the user prefer?"
    assert "Neovim" in ex["messages"][2]["content"]


def test_export_filters_low_reliability_and_short(tmp_path):
    conn = _make_lessons_db(
        [
            (None, "Reliable long lesson about deployment workflows here.", 0.9),
            (None, "Unreliable lesson that should be filtered out entirely.", 0.1),
            (None, "too short", 1.0),
        ]
    )
    out = str(tmp_path / "ds.jsonl")
    n = LoraDatasetExporter(conn, LoraConfig(min_reliability=0.5)).export(out)
    assert n == 1


def test_export_deduplicates(tmp_path):
    rows = [(None, "The user deploys with docker compose on port 8080.", 1.0)] * 3
    conn = _make_lessons_db(rows)
    out = str(tmp_path / "ds.jsonl")
    n = LoraDatasetExporter(conn).export(out)
    assert n == 1


def test_trainer_degrades_without_ml_stack(tmp_path, monkeypatch):
    import viki.core.forge_lora as forge_lora

    monkeypatch.setattr(
        forge_lora, "ml_stack_available", lambda: (False, "pip install torch peft trl")
    )
    ds = tmp_path / "ds.jsonl"
    ds.write_text('{"messages": []}\n')
    result = LoraTrainer(LoraConfig(output_dir=str(tmp_path / "out"))).train(str(ds))
    assert result["status"] == "unavailable"
    assert "pip install" in result["reason"]


def test_write_adapter_modelfile(tmp_path):
    adapter = tmp_path / "adapter"
    adapter.mkdir()
    mf = str(tmp_path / "Modelfile.viki-lora")
    write_adapter_modelfile("phi3:mini", str(adapter), mf, system_prompt="Test prompt")
    content = open(mf).read()
    assert content.startswith("FROM phi3:mini\n")
    assert f"ADAPTER {os.path.abspath(str(adapter))}" in content
    assert "Test prompt" in content

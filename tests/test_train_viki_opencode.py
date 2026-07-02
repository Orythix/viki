"""
Tests for scripts/train_viki_opencode.py.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.train_viki_opencode as train_viki_opencode
from viki.core.knowledge_ingestion import LearningModule


class TestTrainVikiOpencode(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.temp_dir = Path(self._td.name)
        self.data_dir = self.temp_dir / "data"
        self.data_dir.mkdir(exist_ok=True)
        self.config_dir = self.temp_dir / "config"
        self.config_dir.mkdir(exist_ok=True)

        # Write a mock seed file
        self.seed_path = self.config_dir / "knowledge_seed.jsonl"
        with open(self.seed_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"trigger": "hello", "fact": "world"}) + "\n")

        self.output_path = self.data_dir / "training_dataset_opencode.jsonl"

        # Intercept and track sqlite3 connections to prevent Windows file locking
        self.connections = []
        orig_connect = sqlite3.connect

        def mock_connect(*args, **kwargs):
            conn = orig_connect(*args, **kwargs)
            self.connections.append(conn)
            return conn

        self.connect_patcher = patch("sqlite3.connect", side_effect=mock_connect)
        self.connect_patcher.start()

    def tearDown(self):
        self.connect_patcher.stop()
        for conn in self.connections:
            try:
                conn.close()
            except Exception:
                pass
        try:
            self._td.cleanup()
        except Exception:
            pass

    def test_workflow(self):
        with patch.object(train_viki_opencode, "DATA_DIR", self.data_dir), patch.object(
            train_viki_opencode, "CONFIG_DIR", self.config_dir
        ), patch.object(train_viki_opencode, "KNOWLEDGE_SEED", self.seed_path), patch.object(
            train_viki_opencode, "TRAINING_OUTPUT", self.output_path
        ), patch.object(train_viki_opencode, "REPO_ROOT", self.temp_dir):
            # Run the main function
            train_viki_opencode.main()

            # Assert file creations
            self.assertTrue(self.output_path.exists())
            enhanced_output = self.data_dir / "training_enhanced.jsonl"
            self.assertTrue(enhanced_output.exists())

            # Verify database content
            learning = LearningModule(str(self.data_dir))
            self.assertGreaterEqual(learning.get_total_lesson_count(), 1)


if __name__ == "__main__":
    unittest.main()

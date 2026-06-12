"""
Tests for scripts/build_viki_model.py.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

# Add repo root and src/viki to path so we can import scripts and viki packages correctly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src" / "viki"))

import scripts.build_viki_model as build_viki_model


class TestBuildVikiModel(unittest.TestCase):
    def setUp(self):
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

    def test_parse_args(self):
        with patch("sys.argv", ["build_viki_model", "--strategy", "lora", "--steps", "120"]):
            args = build_viki_model.parse_args()
            self.assertEqual(args.strategy, "lora")
            self.assertEqual(args.steps, 120)

    def test_resolve_base_model(self):
        # Explicit CLI value
        self.assertEqual(build_viki_model.resolve_base_model("custom", {}), "custom")

        # Env var override
        with patch.dict(os.environ, {"VIKI_FORGE_BASE_OLLAMA_MODEL": "env-model"}):
            self.assertEqual(build_viki_model.resolve_base_model(None, {}), "env-model")

        # Config fallback
        settings = {"system": {"forge_base_ollama_model": "config-model"}}
        self.assertEqual(build_viki_model.resolve_base_model(None, settings), "config-model")

        # Default fallback
        self.assertEqual(build_viki_model.resolve_base_model(None, {}), "qwen3.6:latest")

    def test_resolve_data_dir(self):
        # Explicit CLI value
        with tempfile.TemporaryDirectory() as td:
            d = build_viki_model.resolve_data_dir(td, {})
            self.assertTrue(d.samefile(Path(td)))

        # Env var override
        with tempfile.TemporaryDirectory() as td:
            with patch.dict(os.environ, {"VIKI_DATA_DIR": td}):
                d = build_viki_model.resolve_data_dir(None, {})
                self.assertTrue(d.samefile(Path(td)))

    @patch("shutil.which")
    @patch("scripts.build_viki_model._run")
    def test_ollama_available(self, mock_run, mock_which):
        # Not on PATH
        mock_which.return_value = None
        avail, msg = build_viki_model.ollama_available()
        self.assertFalse(avail)
        self.assertIn("not on PATH", msg)

        # Daemon not reachable
        mock_which.return_value = "ollama"
        mock_run.return_value = SimpleNamespace(returncode=1, stderr="connection refused")
        avail, msg = build_viki_model.ollama_available()
        self.assertFalse(avail)
        self.assertIn("not reachable", msg)

        # Success
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="models list")
        avail, msg = build_viki_model.ollama_available()
        self.assertTrue(avail)

    @patch("scripts.build_viki_model._run")
    def test_ollama_has_model(self, mock_run):
        mock_run.return_value = SimpleNamespace(
            returncode=0, stdout="NAME\nllama3:latest\nqwen3.6:latest\n"
        )
        self.assertTrue(build_viki_model.ollama_has_model("qwen3.6:latest"))
        self.assertFalse(build_viki_model.ollama_has_model("phi3:latest"))

    @patch("scripts.build_viki_model.ollama_create")
    @patch("viki.core.knowledge_ingestion.LearningModule")
    def test_strategy_prompt_bake(self, mock_lm, mock_create):
        # Failure: no frequent lessons
        lm_instance = mock_lm.return_value
        lm_instance.get_frequent_lessons.return_value = []
        with tempfile.TemporaryDirectory() as td:
            rc = build_viki_model.strategy_prompt_bake(
                base_model="base", tag="tag", data_dir=Path(td), min_count=2, dry_run=False
            )
            self.assertEqual(rc, 2)

        # Success
        lm_instance.get_frequent_lessons.return_value = ["lesson A", "lesson B"]
        mock_create.return_value = (True, "success output")
        with tempfile.TemporaryDirectory() as td:
            rc = build_viki_model.strategy_prompt_bake(
                base_model="base", tag="tag", data_dir=Path(td), min_count=2, dry_run=False
            )
            self.assertEqual(rc, 0)
            modelfile = Path(td) / "Modelfile.viki_evolved"
            self.assertTrue(modelfile.exists())
            self.assertIn("lesson A", modelfile.read_text(encoding="utf-8"))

    def test_strategy_lora(self):
        # Skipped if env not set
        with patch.dict(os.environ, {"VIKI_UNSLOTH_RUN_TRAIN": "0"}):
            with tempfile.TemporaryDirectory() as td:
                rc = build_viki_model.strategy_lora(
                    data_dir=Path(td), dataset_path=Path(td) / "ds.jsonl", steps=10, dry_run=False
                )
                self.assertEqual(rc, 0)

        # Run training successfully
        with patch.dict(os.environ, {"VIKI_UNSLOTH_RUN_TRAIN": "1"}):
            with patch("skills.creation.forge._unsloth_train_sync") as mock_train:
                mock_train.return_value = "LoRA: adapter saved to output"
                with tempfile.TemporaryDirectory() as td:
                    rc = build_viki_model.strategy_lora(
                        data_dir=Path(td),
                        dataset_path=Path(td) / "ds.jsonl",
                        steps=10,
                        dry_run=False,
                    )
                    self.assertEqual(rc, 0)

    @patch("viki.core.knowledge_ingestion.LearningModule")
    @patch("viki.core.preference_forge.PreferenceDatasetBuilder")
    @patch("viki.core.preference_forge.run_dpo_training")
    @patch("viki.core.preference_forge.trl_dpo_available")
    def test_strategy_preference(self, mock_trl_dpo, mock_dpo_train, mock_builder_cls, mock_lm):
        builder = mock_builder_cls.return_value

        # No pairs
        builder.build.return_value = ("No preference pairs available.", 0)
        with tempfile.TemporaryDirectory() as td:
            rc = build_viki_model.strategy_preference(
                method="dpo", data_dir=Path(td), steps=10, dry_run=False
            )
            self.assertEqual(rc, 6)

        # Run training successfully
        builder.build.return_value = ("Wrote 5 pairs", 5)
        mock_trl_dpo.return_value = True
        mock_dpo_train.return_value = "PreferenceForge: DPO adapter saved"
        with patch.dict(os.environ, {"VIKI_DPO_RUN_TRAIN": "1"}):
            with tempfile.TemporaryDirectory() as td:
                rc = build_viki_model.strategy_preference(
                    method="dpo", data_dir=Path(td), steps=10, dry_run=False
                )
                self.assertEqual(rc, 0)

    def test_set_default_profile(self):
        with tempfile.TemporaryDirectory() as td:
            config_dir = Path(td) / "config"
            config_dir.mkdir()
            models_yaml = config_dir / "models.yaml"
            models_yaml.write_text("models:\n  default: old-model\n", encoding="utf-8")

            with patch("scripts.build_viki_model.REPO_ROOT", Path(td)):
                success = build_viki_model.set_default_profile("new-model")
                self.assertTrue(success)
                self.assertIn("default: new-model", models_yaml.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

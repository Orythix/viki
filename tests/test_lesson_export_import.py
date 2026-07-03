"""LearningModule export threshold and JSONL import."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest

from viki.core.knowledge_ingestion import LearningModule


class TestLessonExportImport(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.lm = LearningModule(self.td)

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def test_resolve_export_min_access_explicit(self):
        self.assertEqual(LearningModule.resolve_export_min_access_count(3), 3)
        self.assertEqual(LearningModule.resolve_export_min_access_count(1), 1)

    def test_resolve_export_from_settings(self):
        s = {"system": {"lesson_export_min_access_count": 1}}
        self.assertEqual(LearningModule.resolve_export_min_access_count(settings=s), 1)

    def test_export_respects_min_threshold(self):
        out = os.path.join(self.td, "out.jsonl")
        self.lm.save_lesson(trigger="t1", fact="f1", source_task="test")
        msg = self.lm.export_training_dataset(out, min_access_count=2)
        self.assertIn("No lessons", msg)
        self.assertFalse(os.path.isfile(out))
        self.lm.save_lesson(trigger="t1", fact="f1", source_task="test")
        msg = self.lm.export_training_dataset(out, min_access_count=2)
        self.assertIn("Exported 1", msg)
        self.assertTrue(os.path.isfile(out))

    def test_import_jsonl_trigger_fact(self):
        path = os.path.join(self.td, "in.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"trigger": "Q", "fact": "Answer text long enough."}) + "\n")
        msg = self.lm.import_lessons_from_jsonl(path, reinforce=True)
        self.assertIn("Imported 1", msg)
        cur = self.lm.conn.cursor()
        cur.execute("SELECT access_count FROM lessons")
        row = cur.fetchone()
        self.assertIsNotNone(row)
        self.assertGreaterEqual(row[0], 2)

    def test_import_jsonl_per_row_source_author_reliability(self):
        path = os.path.join(self.td, "meta.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "trigger": "ROW_META",
                        "fact": "Per-row metadata must flow into the lessons table.",
                        "source_task": "https://example.com/doc",
                        "author": "Tester",
                        "reliability": 0.91,
                    }
                )
                + "\n"
            )
        msg = self.lm.import_lessons_from_jsonl(path, source_task="fallback_default")
        self.assertIn("Imported 1", msg)
        cur = self.lm.conn.cursor()
        cur.execute("SELECT source_task, author, reliability FROM lessons LIMIT 1")
        row = cur.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "https://example.com/doc")
        self.assertEqual(row[1], "Tester")
        self.assertAlmostEqual(row[2], 0.91, places=2)


if __name__ == "__main__":
    unittest.main()

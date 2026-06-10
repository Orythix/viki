"""
P1: tests for TimeTravelModule.undo_last and the /undo path.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from types import SimpleNamespace

from viki.core.temporal_memory import TimeTravelModule


class _FakeWorking:
    def get_trace(self):
        return []


class _FakeMemory:
    def __init__(self):
        self.working = _FakeWorking()


class TestUndoLast(unittest.TestCase):
    def test_undo_restores_last_checkpoint(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            target = os.path.join(td, "code.py")
            with open(target, "w", encoding="utf-8") as f:
                f.write("ORIGINAL")
            ttm = TimeTravelModule(td)
            controller = SimpleNamespace(memory=_FakeMemory())
            cid = ttm.create_checkpoint(controller, "filesystem_skill", {"path": target})
            self.assertTrue(cid)
            with open(target, "w", encoding="utf-8") as f:
                f.write("CHANGED")
            ok, restored, _ = ttm.undo_last()
            self.assertTrue(ok)
            self.assertIn(os.path.abspath(target), restored)
            with open(target, "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), "ORIGINAL")
            ttm.close()

    def test_undo_with_no_checkpoints(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            ttm = TimeTravelModule(td)
            ok, restored, msg = ttm.undo_last()
            self.assertFalse(ok)
            self.assertEqual(restored, [])
            self.assertIn("No checkpoints", msg)
            ttm.close()


if __name__ == "__main__":
    unittest.main()

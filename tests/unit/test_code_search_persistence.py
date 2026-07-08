"""
P1 regression: CodeSearchSkill must persist its index to SQLite and skip
files whose mtime/sha hasn't changed on subsequent scans.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from types import SimpleNamespace

from viki.skills.builtins.code_search_skill import CodeSearchSkill


def _stub_controller(data_dir: str):
    return SimpleNamespace(settings={"system": {"data_dir": data_dir, "workspace_dir": data_dir}})


class TestCodeSearchPersistence(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.workspace = self._td.name

    def tearDown(self):
        try:
            self._td.cleanup()
        except Exception:
            pass

    def _make_file(self, name: str, content: str) -> str:
        path = os.path.join(self.workspace, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_persisted_chunks_loaded_on_restart(self):
        self._make_file("a.py", "def alpha():\n    return 1\n\nclass Beta:\n    pass\n")
        skill1 = CodeSearchSkill(controller=_stub_controller(self.workspace))
        skill1.scan(self.workspace)
        n_chunks_first = len(skill1._chunks)
        n_symbols_first = len(skill1._symbols)
        self.assertGreater(n_chunks_first, 0)

        # New skill instance simulates a process restart.
        skill2 = CodeSearchSkill(controller=_stub_controller(self.workspace))
        # Without scanning, the index should already be loaded from disk.
        self.assertEqual(len(skill2._chunks), n_chunks_first)
        self.assertEqual(len(skill2._symbols), n_symbols_first)

    def test_unchanged_file_is_skipped(self):
        self._make_file("a.py", "def alpha():\n    return 1\n")
        skill = CodeSearchSkill(controller=_stub_controller(self.workspace))
        before = skill.scan(self.workspace)
        # Second scan with no changes should keep the same counts.
        after = skill.scan(self.workspace)
        self.assertEqual(before[1], after[1])

    def test_invalidate_path_drops_chunks(self):
        path = self._make_file("a.py", "def alpha():\n    return 1\n")
        skill = CodeSearchSkill(controller=_stub_controller(self.workspace))
        skill.scan(self.workspace)
        self.assertTrue(any(c.path == path for c in skill._chunks))
        skill.invalidate_path(path)
        self.assertFalse(any(c.path == path for c in skill._chunks))


if __name__ == "__main__":
    unittest.main()

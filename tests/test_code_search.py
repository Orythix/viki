"""
Phase 3: tests for CodeSearchSkill (regex chunker, lexical & semantic ranking).
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import textwrap
import unittest

from skills.builtins.code_search_skill import CodeSearchSkill


def _run(coro):
    return asyncio.run(coro)


class TestCodeSearch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._write(
            "viki_app/auth.py",
            textwrap.dedent(
                """
                import hashlib

                class AuthService:
                    def __init__(self):
                        self.users = {}

                    def hash_password(self, password: str) -> str:
                        return hashlib.sha256(password.encode()).hexdigest()

                    def verify_password(self, raw, hashed):
                        return self.hash_password(raw) == hashed
                """
            ),
        )
        self._write(
            "viki_app/utils.py",
            textwrap.dedent(
                """
                def slugify(s: str) -> str:
                    return s.lower().replace(' ', '-')
                """
            ),
        )

    def tearDown(self):
        for root, _, files in os.walk(self.tmp, topdown=False):
            for f in files:
                os.unlink(os.path.join(root, f))
            os.rmdir(root)

    def _write(self, rel: str, content: str) -> None:
        path = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content.strip() + "\n")

    def test_scan_indexes_files(self):
        skill = CodeSearchSkill(controller=None)
        n_files, n_chunks, n_symbols = skill.scan(self.tmp)
        self.assertEqual(n_files, 2)
        self.assertGreaterEqual(n_chunks, 2)
        self.assertGreaterEqual(n_symbols, 3)

    def test_search_finds_relevant_chunk(self):
        skill = CodeSearchSkill(controller=None)
        skill.scan(self.tmp)
        results = skill.search("hash password sha256", top_k=3)
        self.assertTrue(results)
        self.assertTrue(any("hash_password" in r.text for r in results))

    def test_find_symbol(self):
        skill = CodeSearchSkill(controller=None)
        skill.scan(self.tmp)
        hits = skill.find_symbol("AuthService")
        self.assertTrue(hits)
        self.assertEqual(hits[0].name, "AuthService")
        self.assertEqual(hits[0].kind, "class")

    def test_skill_action_search_returns_json(self):
        skill = CodeSearchSkill(controller=None)
        skill.scan(self.tmp)
        out = _run(skill.execute({"action": "search", "query": "slugify", "top_k": 2}))
        parsed = json.loads(out)
        self.assertIsInstance(parsed, list)
        self.assertGreaterEqual(len(parsed), 1)


if __name__ == "__main__":
    unittest.main()

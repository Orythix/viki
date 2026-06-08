"""
Phase 6: tests for the vector memory backend selector + numpy / lexical paths.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from core.vector_memory import (
    VectorHit,
    build_vector_backend,
)


class TestVectorBackendSelection(unittest.TestCase):
    def test_numpy_backend_when_no_db(self):
        be = build_vector_backend(dim=4, db_path=None, prefer=["numpy-memory", "lexical-fallback"])
        self.assertIn(be.backend_name, ("numpy-memory", "lexical-fallback"))

    def test_lexical_fallback_returns_empty_without_query_text(self):
        # P0 fix regression: previously the lexical fallback returned the
        # last-N rows (recency bias). Without query_text we now return [] so
        # the caller's own lexical ranker can take over.
        be = build_vector_backend(dim=4, prefer=["lexical-fallback"])
        self.assertEqual(be.backend_name, "lexical-fallback")
        be.upsert(1, [0.0] * 4, "hello world")
        be.upsert(2, [0.0] * 4, "goodbye world")
        hits = be.search([0.0] * 4, top_k=2)
        self.assertEqual(hits, [])

    def test_lexical_fallback_token_overlap_ranks(self):
        be = build_vector_backend(dim=4, prefer=["lexical-fallback"])
        be.upsert(1, [0.0] * 4, "Configure the Postgres database connection.")
        be.upsert(2, [0.0] * 4, "Bake the cake at 350F for 30 minutes.")
        be.upsert(3, [0.0] * 4, "Postgres replication setup steps.")
        hits = be.search([0.0] * 4, top_k=2, query_text="postgres setup")
        self.assertGreaterEqual(len(hits), 1)
        # The cake recipe must NOT win.
        self.assertNotIn(2, [h.id for h in hits])
        # Postgres-related entries should be on top.
        self.assertIn(hits[0].id, (1, 3))

    def test_numpy_backend_search_is_sane(self):
        try:
            import numpy  # noqa: F401
        except Exception:
            self.skipTest("numpy not available")
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            snap = os.path.join(td, "v.sqlite")
            be = build_vector_backend(dim=3, db_path=snap, prefer=["numpy-memory"])
            be.upsert(1, [1.0, 0.0, 0.0], "x-axis")
            be.upsert(2, [0.0, 1.0, 0.0], "y-axis")
            be.upsert(3, [0.0, 0.0, 1.0], "z-axis")
            hits = be.search([0.9, 0.1, 0.0], top_k=2)
            self.assertEqual(hits[0].text, "x-axis")
            ids = [h.id for h in hits]
            self.assertIn(1, ids)


class TestNumpyBackendPersistence(unittest.TestCase):
    def test_round_trip(self):
        try:
            import numpy  # noqa: F401
        except Exception:
            self.skipTest("numpy not available")
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            snap = os.path.join(td, "v.sqlite")
            be1 = build_vector_backend(dim=2, db_path=snap, prefer=["numpy-memory"])
            be1.upsert(1, [1.0, 0.0], "alpha")
            be1.upsert(2, [0.0, 1.0], "beta")
            be2 = build_vector_backend(dim=2, db_path=snap, prefer=["numpy-memory"])
            stats = be2.stats()
            self.assertGreaterEqual(stats["count"], 2)
            hits = be2.search([1.0, 0.0], top_k=1)
            self.assertEqual(hits[0].text, "alpha")


if __name__ == "__main__":
    unittest.main()

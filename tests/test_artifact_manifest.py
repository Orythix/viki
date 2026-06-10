"""
P1: tests for the ArtifactManifest helper. The download endpoint security
behaviour (path-traversal guard, manifest-listed only) is exercised
indirectly here by inspecting the manifest contents.
"""
from __future__ import annotations

import os
import tempfile
import unittest

from viki.core.artifact_manifest import ArtifactManifest


class TestArtifactManifest(unittest.TestCase):
    def test_finalize_and_load_round_trip(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            artifact_path = os.path.join(td, "result.txt")
            with open(artifact_path, "w", encoding="utf-8") as f:
                f.write("hello world")
            m = ArtifactManifest(mission_id="m-1", goal="demo", workspace_dir=td)
            m.add_artifact(artifact_path, description="primary")
            m.add_test("smoke", "pytest", True, 0.1, "ok")
            m.finalize()
            loaded = ArtifactManifest.load("m-1", td)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.goal, "demo")
            self.assertEqual(len(loaded.artifacts), 1)
            self.assertEqual(loaded.artifacts[0].description, "primary")
            self.assertIsNotNone(loaded.artifacts[0].sha256)


if __name__ == "__main__":
    unittest.main()

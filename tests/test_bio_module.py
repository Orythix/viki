"""
P2: tests for BioModule. We don't open a real camera; we just confirm the
backend/experimental flag wiring and that the deepface fallback degrades to
'neutral' when the package is missing.
"""
from __future__ import annotations

import unittest

from core.biometric_service import BioModule


class TestBioModule(unittest.TestCase):
    def test_default_is_experimental(self):
        bio = BioModule(webcam_enabled=False)
        self.assertTrue(bio.experimental)
        self.assertEqual(bio.get_state(), "neutral")

    def test_deepface_backend_marks_non_experimental(self):
        bio = BioModule(webcam_enabled=False, backend="deepface")
        self.assertFalse(bio.experimental)

    def test_deepface_missing_package_returns_neutral(self):
        bio = BioModule(webcam_enabled=False, backend="deepface")
        # Force the lazy loader path with deliberately missing module.
        result = bio._analyze_deepface(frame=None)
        self.assertEqual(result, "neutral")
        self.assertTrue(bio._deepface_load_failed)


if __name__ == "__main__":
    unittest.main()

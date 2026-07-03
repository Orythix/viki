"""
Lazy sentence-transformer encoder.

LearningModule and NarrativeMemory must NOT import sentence_transformers
during __init__. The import / instantiation should only happen the first time
a non-trivial query asks for an embedding.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from unittest.mock import patch


def _module_loaded(name: str) -> bool:
    return name in sys.modules


class TestLazyEncoder(unittest.TestCase):
    def setUp(self):
        # Drop any prior import so we can observe a fresh boot.
        sys.modules.pop("sentence_transformers", None)
        self._td = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)

    def tearDown(self):
        try:
            self._td.cleanup()
        except Exception:
            pass

    def test_learning_module_does_not_eager_load_encoder(self):
        """Constructing LearningModule shouldn't touch the encoder property."""
        from viki.core.knowledge_ingestion import LearningModule

        # The encoder should still be unloaded after init.
        lm = LearningModule(self._td.name)
        self.assertFalse(lm._encoder_loaded, "encoder should not load during __init__")

    def test_narrative_memory_does_not_eager_load_encoder(self):
        from viki.core.memory.narrative import NarrativeMemory

        nm = NarrativeMemory(self._td.name)
        self.assertFalse(nm._encoder_loaded, "encoder should not load during __init__")

    def test_encoder_loads_on_first_access(self):
        """Accessing the property triggers `get_encoder`."""
        from viki.core.knowledge_ingestion import LearningModule

        lm = LearningModule(self._td.name)
        with patch("viki.core.embeddings.get_encoder", return_value=object()) as mock_get:
            _ = lm.encoder
            _ = lm.encoder  # second call must NOT re-trigger
            mock_get.assert_called_once()
        self.assertTrue(lm._encoder_loaded)


if __name__ == "__main__":
    unittest.main()

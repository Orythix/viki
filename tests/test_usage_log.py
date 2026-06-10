import json
import os
import tempfile
import unittest

from viki.core.usage_log import (
    configure_session_usage_log,
    emit_llm_inference,
    emit_model_feedback,
    emit_skill_execution,
    USAGE_FILENAME,
)


class _FakeProvider:
    def __init__(self):
        self.model_name = "test-model"
        self.trust_score = 1.0
        self.call_count = 0


class TestUsageLog(unittest.TestCase):
    def tearDown(self):
        configure_session_usage_log(os.getcwd(), False)

    def test_disabled_writes_nothing(self):
        d = tempfile.mkdtemp()
        try:
            configure_session_usage_log(d, False)
            emit_skill_execution("noop", 0.01, True, None)
            path = os.path.join(d, USAGE_FILENAME)
            self.assertFalse(os.path.isfile(path))
        finally:
            configure_session_usage_log(os.getcwd(), False)

    def test_jsonl_roundtrip(self):
        d = tempfile.mkdtemp()
        try:
            configure_session_usage_log(d, True)
            p = _FakeProvider()
            emit_llm_inference(p, 0.002, True, "chat")
            emit_model_feedback(p, 0.0, True)
            emit_skill_execution("demo_skill", 0.05, True, None)

            path = os.path.join(d, USAGE_FILENAME)
            self.assertTrue(os.path.isfile(path))
            with open(path, "r", encoding="utf-8") as f:
                lines = [ln.strip() for ln in f if ln.strip()]
            self.assertEqual(len(lines), 3)
            ev = [json.loads(ln)["event"] for ln in lines]
            self.assertEqual(ev, ["llm_inference", "model_feedback", "skill_execution"])
        finally:
            configure_session_usage_log(os.getcwd(), False)

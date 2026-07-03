"""
P1: tests for the attachment perception stage.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from types import SimpleNamespace

from viki.core.request_pipeline import RequestContext, _AttachmentStage


def _run(coro):
    return asyncio.run(coro)


class _FakeVisionSkill:
    async def execute(self, params):
        return f"VISION:{os.path.basename(params.get('image_path') or params.get('path'))}"


class _FakeWhisperSkill:
    async def execute(self, params):
        return f"WHISPER:{os.path.basename(params.get('audio_path') or params.get('path'))}"


class _FakeRegistry:
    def __init__(self, mapping):
        self._m = mapping

    def get_skill(self, name):
        return self._m.get(name)


class TestAttachmentStage(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.dir = self._td.name
        self.image = os.path.join(self.dir, "shot.png")
        self.audio = os.path.join(self.dir, "clip.wav")
        self.text = os.path.join(self.dir, "notes.md")
        for p, c in ((self.image, b"\x89PNG\r\n"), (self.audio, b"RIFF"), (self.text, b"hello md")):
            with open(p, "wb") as f:
                f.write(c)

    def tearDown(self):
        try:
            self._td.cleanup()
        except Exception:
            pass

    def test_image_routes_through_vision_skill(self):
        ctrl = SimpleNamespace(skill_registry=_FakeRegistry({"vision": _FakeVisionSkill()}))
        ctx = RequestContext(user_input="describe", session_id="s", attachment_paths=[self.image])
        _run(_AttachmentStage().run(ctrl, ctx))
        self.assertIn("VISION:shot.png", ctx.user_input)
        self.assertIn("describe", ctx.user_input)

    def test_audio_routes_through_whisper(self):
        ctrl = SimpleNamespace(skill_registry=_FakeRegistry({"whisper": _FakeWhisperSkill()}))
        ctx = RequestContext(user_input="transcribe", session_id="s", attachment_paths=[self.audio])
        _run(_AttachmentStage().run(ctrl, ctx))
        self.assertIn("WHISPER:clip.wav", ctx.user_input)

    def test_text_inlined(self):
        ctrl = SimpleNamespace(skill_registry=_FakeRegistry({}))
        ctx = RequestContext(user_input="ack", session_id="s", attachment_paths=[self.text])
        _run(_AttachmentStage().run(ctrl, ctx))
        self.assertIn("hello md", ctx.user_input)

    def test_no_skill_yields_graceful_message(self):
        ctrl = SimpleNamespace(skill_registry=_FakeRegistry({}))
        ctx = RequestContext(user_input="ack", session_id="s", attachment_paths=[self.image])
        _run(_AttachmentStage().run(ctrl, ctx))
        self.assertIn("no vision skill", ctx.user_input)


if __name__ == "__main__":
    unittest.main()

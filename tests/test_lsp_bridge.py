"""
Tests for the LSP bridge JSON-RPC handling.

We deliberately don't depend on a real `pyright` / `tsserver` binary in CI.
Instead we monkey-patch `LSPSession._write_message` and feed crafted server
responses through the existing `_pending` future map, exercising the same
code paths a real server would hit (publishDiagnostics, hover, references,
definition).
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from typing import Any

from viki.integrations.lsp_bridge import LSPSession, LSPSpec, _path_to_uri


def _run(coro):
    return (
        asyncio.get_event_loop().run_until_complete(coro)
        if not asyncio.get_event_loop().is_running()
        else asyncio.run(coro)
    )


class _FakeLSPSession(LSPSession):
    """LSPSession with the subprocess replaced by an in-memory queue."""

    def __init__(self, spec: LSPSpec, workspace_dir: str):
        super().__init__(spec, workspace_dir)
        self.outbound: list = []
        self._fake_alive = True

    @property
    def is_alive(self) -> bool:  # type: ignore[override]
        return self._fake_alive

    async def _write_message(self, payload: dict[str, Any]) -> None:  # type: ignore[override]
        self.outbound.append(payload)

    def deliver_response(self, msg_id: int, result: Any) -> None:
        fut = self._pending.pop(msg_id, None)
        if fut and not fut.done():
            fut.set_result(result)

    def deliver_diagnostics(self, uri: str, diagnostics: list) -> None:
        # Mirror LSPSession._read_loop's publishDiagnostics handling.
        self._diagnostics[uri] = list(diagnostics)


class TestLSPBridge(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.workspace = self._td.name
        self.file_path = os.path.join(self.workspace, "demo.py")
        with open(self.file_path, "w", encoding="utf-8") as f:
            f.write("def foo():\n    return 1\n")
        self.session = _FakeLSPSession(
            LSPSpec(name="fake", command=["fake-lsp"], extensions=[".py"]),
            self.workspace,
        )

    def tearDown(self):
        try:
            self._td.cleanup()
        except Exception:
            pass

    async def test_diagnostics_capture(self):
        uri = _path_to_uri(self.file_path)
        self.session.deliver_diagnostics(
            uri,
            [{"severity": 1, "message": "syntax error", "range": {}}],
        )
        diags = await self.session.diagnose(self.file_path, wait_seconds=0.2)
        self.assertEqual(len(diags), 1)
        self.assertEqual(diags[0]["message"], "syntax error")

    async def test_hover_request_format(self):
        async def server():
            # Wait for the request to be queued.
            await asyncio.sleep(0.05)
            self.assertEqual(len(self.session.outbound), 2)  # didOpen + hover
            hover_msg = self.session.outbound[1]
            self.assertEqual(hover_msg["method"], "textDocument/hover")
            self.assertIn("position", hover_msg["params"])
            self.session.deliver_response(
                hover_msg["id"],
                {"contents": {"kind": "markdown", "value": "**foo** -> int"}},
            )

        srv = asyncio.create_task(server())
        result = await self.session.hover(self.file_path, line=0, character=4)
        await srv
        self.assertIsNotNone(result)
        self.assertIn("foo", result["text"])

    async def test_references_request_format(self):
        async def server():
            await asyncio.sleep(0.05)
            req = next(
                m for m in self.session.outbound if m.get("method") == "textDocument/references"
            )
            self.assertTrue(req["params"]["context"]["includeDeclaration"])
            self.session.deliver_response(
                req["id"],
                [
                    {
                        "uri": _path_to_uri(self.file_path),
                        "range": {
                            "start": {"line": 0, "character": 4},
                            "end": {"line": 0, "character": 7},
                        },
                    },
                ],
            )

        srv = asyncio.create_task(server())
        refs = await self.session.references(self.file_path, line=0, character=4)
        await srv
        self.assertEqual(len(refs), 1)
        self.assertIn("uri", refs[0])

    async def test_definition_returns_list_when_single(self):
        async def server():
            await asyncio.sleep(0.05)
            req = next(
                m for m in self.session.outbound if m.get("method") == "textDocument/definition"
            )
            self.session.deliver_response(
                req["id"],
                {
                    "uri": _path_to_uri(self.file_path),
                    "range": {
                        "start": {"line": 0, "character": 0},
                        "end": {"line": 0, "character": 3},
                    },
                },
            )

        srv = asyncio.create_task(server())
        defs = await self.session.definition(self.file_path, line=0, character=4)
        await srv
        self.assertEqual(len(defs), 1)


if __name__ == "__main__":
    unittest.main()

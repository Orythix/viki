"""
Phase 3: Language Server Protocol bridge.

Provides VIKI's planner/executor with IDE-grade diagnostics, hovers, and
references for Python / TypeScript / Go without requiring a full editor.

Design:
- The bridge spawns the requested LSP server (e.g. `pyright-langserver --stdio`,
  `typescript-language-server --stdio`, `gopls`) as a subprocess and pumps
  JSON-RPC messages over stdio.
- It is intentionally minimal: we expose only the methods the agent needs
  (`diagnose_file`, `hover`, `references`).
- Servers are launched lazily on first use; misconfigured environments degrade
  to an inert no-op rather than breaking the controller.

This module deliberately does not depend on any third-party LSP client library
to keep the install surface small.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from viki.config.logger import viki_logger


@dataclass
class LSPSpec:
    name: str
    command: List[str]
    extensions: List[str] = field(default_factory=list)


_DEFAULT_SPECS: Dict[str, LSPSpec] = {
    "pyright": LSPSpec(name="pyright", command=["pyright-langserver", "--stdio"], extensions=[".py"]),
    "ts": LSPSpec(name="typescript", command=["typescript-language-server", "--stdio"], extensions=[".ts", ".tsx", ".js", ".jsx"]),
    "go": LSPSpec(name="gopls", command=["gopls"], extensions=[".go"]),
}


def _path_to_uri(path: str) -> str:
    """Convert an absolute filesystem path to an LSP-compatible file URI."""
    abs_path = os.path.abspath(path).replace(os.sep, "/")
    # Windows: drive-letter paths need an extra leading slash, e.g. file:///C:/foo
    if len(abs_path) >= 2 and abs_path[1] == ":":
        return f"file:///{abs_path}"
    return f"file://{abs_path}"


class LSPSession:
    """One running LSP subprocess with JSON-RPC framing."""

    def __init__(self, spec: LSPSpec, workspace_dir: str):
        self.spec = spec
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.proc: Optional[asyncio.subprocess.Process] = None
        self._next_id = 1
        self._pending: Dict[int, asyncio.Future] = {}
        self._reader_task: Optional[asyncio.Task] = None
        # Diagnostics published asynchronously by the server, keyed by URI.
        self._diagnostics: Dict[str, List[Dict[str, Any]]] = {}
        # Open documents (uri -> version) so we send the correct didChange version.
        self._open_docs: Dict[str, int] = {}

    @property
    def is_alive(self) -> bool:
        return self.proc is not None and self.proc.returncode is None

    async def start(self) -> bool:
        if shutil.which(self.spec.command[0]) is None:
            viki_logger.debug("LSP %s: command '%s' not on PATH; skipping.", self.spec.name, self.spec.command[0])
            return False
        try:
            self.proc = await asyncio.create_subprocess_exec(
                *self.spec.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except Exception as e:
            viki_logger.warning("LSP %s: failed to start: %s", self.spec.name, e)
            return False

        self._reader_task = asyncio.create_task(self._read_loop())

        await self._send(
            "initialize",
            {
                "processId": os.getpid(),
                "rootUri": _path_to_uri(self.workspace_dir),
                "capabilities": {
                    "textDocument": {
                        "publishDiagnostics": {"relatedInformation": True},
                        "hover": {"contentFormat": ["markdown", "plaintext"]},
                        "references": {},
                        "definition": {},
                    },
                },
            },
        )
        await self._notify("initialized", {})
        return True

    async def stop(self) -> None:
        try:
            await self._notify("exit", {})
        except Exception:
            pass
        if self.proc and self.proc.returncode is None:
            try:
                self.proc.terminate()
                await asyncio.wait_for(self.proc.wait(), timeout=2)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        if self._reader_task:
            self._reader_task.cancel()

    async def _send(self, method: str, params: Any) -> Any:
        if not self.is_alive:
            return None
        msg_id = self._next_id
        self._next_id += 1
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = fut
        await self._write_message({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params})
        try:
            return await asyncio.wait_for(fut, timeout=10)
        except asyncio.TimeoutError:
            self._pending.pop(msg_id, None)
            return None

    async def _notify(self, method: str, params: Any) -> None:
        if not self.is_alive:
            return
        await self._write_message({"jsonrpc": "2.0", "method": method, "params": params})

    async def _write_message(self, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        if self.proc and self.proc.stdin:
            self.proc.stdin.write(header + body)
            try:
                await self.proc.stdin.drain()
            except Exception:
                pass

    async def _read_loop(self) -> None:
        try:
            assert self.proc and self.proc.stdout is not None
            stdout = self.proc.stdout
            while True:
                header_line = await stdout.readline()
                if not header_line:
                    return
                if not header_line.startswith(b"Content-Length"):
                    continue
                length = int(header_line.split(b":")[1].strip())
                # Skip blank line
                while True:
                    line = await stdout.readline()
                    if line in (b"\r\n", b"\n", b""):
                        break
                body = await stdout.readexactly(length)
                try:
                    payload = json.loads(body)
                except json.JSONDecodeError:
                    continue
                msg_id = payload.get("id")
                method = payload.get("method")
                if msg_id is not None and msg_id in self._pending:
                    fut = self._pending.pop(msg_id)
                    if not fut.done():
                        fut.set_result(payload.get("result") or payload.get("error"))
                elif method == "textDocument/publishDiagnostics":
                    params = payload.get("params") or {}
                    uri = params.get("uri", "")
                    diags = params.get("diagnostics") or []
                    self._diagnostics[uri] = list(diags)
        except asyncio.CancelledError:
            return
        except Exception as e:
            viki_logger.debug("LSP %s reader stopped: %s", self.spec.name, e)

    # --- public-ish queries ---
    async def _ensure_open(self, path: str) -> str:
        """didOpen if first time, else didChange. Returns the doc URI."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            raise RuntimeError(f"unreadable file {path}: {e}") from e
        uri = _path_to_uri(path)
        if uri not in self._open_docs:
            self._open_docs[uri] = 1
            await self._notify(
                "textDocument/didOpen",
                {
                    "textDocument": {
                        "uri": uri,
                        "languageId": _ext_to_language(path),
                        "version": 1,
                        "text": text,
                    }
                },
            )
        else:
            version = self._open_docs[uri] + 1
            self._open_docs[uri] = version
            await self._notify(
                "textDocument/didChange",
                {
                    "textDocument": {"uri": uri, "version": version},
                    "contentChanges": [{"text": text}],
                },
            )
        return uri

    async def diagnose(self, path: str, wait_seconds: float = 1.5) -> List[Dict[str, Any]]:
        """
        Open the file, wait briefly for the server's `publishDiagnostics`, and
        return the latest set. Most servers publish within milliseconds; we use
        a short bounded wait so a quiet server doesn't hang the call.
        """
        try:
            uri = await self._ensure_open(path)
        except RuntimeError as e:
            return [{"severity": "error", "message": str(e)}]
        # Poll for diagnostics with sub-second granularity.
        end = asyncio.get_event_loop().time() + wait_seconds
        while asyncio.get_event_loop().time() < end:
            if uri in self._diagnostics:
                return list(self._diagnostics[uri])
            await asyncio.sleep(0.05)
        return list(self._diagnostics.get(uri, []))

    async def hover(self, path: str, line: int, character: int) -> Optional[Dict[str, Any]]:
        try:
            uri = await self._ensure_open(path)
        except RuntimeError:
            return None
        result = await self._send(
            "textDocument/hover",
            {
                "textDocument": {"uri": uri},
                "position": {"line": int(line), "character": int(character)},
            },
        )
        if not isinstance(result, dict):
            return None
        contents = result.get("contents")
        if isinstance(contents, dict):
            text = contents.get("value", "")
        elif isinstance(contents, list):
            parts = []
            for c in contents:
                if isinstance(c, str):
                    parts.append(c)
                elif isinstance(c, dict) and "value" in c:
                    parts.append(c["value"])
            text = "\n".join(parts)
        elif isinstance(contents, str):
            text = contents
        else:
            text = ""
        return {"text": text, "range": result.get("range")}

    async def references(
        self, path: str, line: int, character: int, include_declaration: bool = True
    ) -> List[Dict[str, Any]]:
        try:
            uri = await self._ensure_open(path)
        except RuntimeError:
            return []
        result = await self._send(
            "textDocument/references",
            {
                "textDocument": {"uri": uri},
                "position": {"line": int(line), "character": int(character)},
                "context": {"includeDeclaration": bool(include_declaration)},
            },
        )
        if not isinstance(result, list):
            return []
        return result

    async def definition(self, path: str, line: int, character: int) -> List[Dict[str, Any]]:
        try:
            uri = await self._ensure_open(path)
        except RuntimeError:
            return []
        result = await self._send(
            "textDocument/definition",
            {
                "textDocument": {"uri": uri},
                "position": {"line": int(line), "character": int(character)},
            },
        )
        if isinstance(result, dict):
            return [result]
        if isinstance(result, list):
            return result
        return []


class LSPBridge:
    """Pool of LSP sessions keyed by file extension."""

    def __init__(self, workspace_dir: str, specs: Optional[Dict[str, LSPSpec]] = None):
        self.workspace_dir = workspace_dir
        self.specs = specs or _DEFAULT_SPECS
        self.sessions: Dict[str, LSPSession] = {}

    def _spec_for_path(self, path: str) -> Optional[LSPSpec]:
        ext = os.path.splitext(path)[1].lower()
        for spec in self.specs.values():
            if ext in spec.extensions:
                return spec
        return None

    async def session_for(self, path: str) -> Optional[LSPSession]:
        spec = self._spec_for_path(path)
        if spec is None:
            return None
        if spec.name not in self.sessions:
            sess = LSPSession(spec, self.workspace_dir)
            ok = await sess.start()
            if not ok:
                return None
            self.sessions[spec.name] = sess
        return self.sessions[spec.name]

    async def diagnose_file(self, path: str) -> List[Dict[str, Any]]:
        session = await self.session_for(path)
        if session is None:
            return [{"severity": "info", "message": "no LSP available"}]
        return await session.diagnose(path)

    async def hover(self, path: str, line: int, character: int) -> Optional[Dict[str, Any]]:
        session = await self.session_for(path)
        if session is None:
            return None
        return await session.hover(path, line, character)

    async def references(
        self, path: str, line: int, character: int, include_declaration: bool = True
    ) -> List[Dict[str, Any]]:
        session = await self.session_for(path)
        if session is None:
            return []
        return await session.references(path, line, character, include_declaration)

    async def definition(self, path: str, line: int, character: int) -> List[Dict[str, Any]]:
        session = await self.session_for(path)
        if session is None:
            return []
        return await session.definition(path, line, character)

    async def shutdown(self) -> None:
        for sess in list(self.sessions.values()):
            try:
                await sess.stop()
            except Exception:
                pass
        self.sessions.clear()


def _ext_to_language(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".py":
        return "python"
    if ext in (".ts", ".tsx"):
        return "typescript"
    if ext in (".js", ".jsx"):
        return "javascript"
    if ext == ".go":
        return "go"
    return "plaintext"

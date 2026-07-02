"""
Phase 3: repo-aware code search.

Indexes the workspace into a symbol graph (file -> symbols + cross-refs) using
tree-sitter when available, with a regex fallback for environments where the
tree-sitter wheels aren't present. Embeds chunks via the existing encoder
(`viki.core.embeddings.get_encoder`) for semantic ranking.

Skill API:
    code_search.search(query: str, top_k: int = 5)              -> ranked snippets
    code_search.symbol(name: str, language: str = "python")     -> symbol locations
    code_search.scan(workspace_dir: str | None = None)          -> rebuild the index

Replaces the ad-hoc grep paths in `dev_skill.py` for repo-level queries.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, cast

from viki.config.logger import viki_logger
from viki.skills.base import BaseSkill

_PY_DEF_RE = re.compile(r"^\s*(?:async\s+)?def\s+(?P<name>\w+)\s*\(", re.MULTILINE)
_PY_CLASS_RE = re.compile(r"^\s*class\s+(?P<name>\w+)\s*[\(:]", re.MULTILINE)
_TS_FN_RE = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?function\s+(?P<name>\w+)\s*\(", re.MULTILINE
)
_TS_CLASS_RE = re.compile(r"^\s*(?:export\s+)?class\s+(?P<name>\w+)\b", re.MULTILINE)


@dataclass
class CodeChunk:
    path: str
    start_line: int
    end_line: int
    language: str
    text: str
    symbol: str | None = None
    embedding: list[float] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "language": self.language,
            "symbol": self.symbol,
            "preview": self.text[:200],
        }


@dataclass
class SymbolEntry:
    name: str
    path: str
    line: int
    language: str
    kind: str  # "function" | "class"


class CodeSearchSkill(BaseSkill):
    EXTENSIONS = {
        ".py": "python",
        ".pyi": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".go": "go",
        ".java": "java",
        ".rb": "ruby",
        ".rs": "rust",
        ".c": "c",
        ".h": "c",
        ".cpp": "cpp",
        ".hpp": "cpp",
        ".cs": "csharp",
    }
    IGNORE_DIRS = {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        "dist",
        "build",
        ".tox",
        ".cursor",
        ".pytest_cache",
    }
    MAX_CHUNK_LINES = 60

    def __init__(self, controller=None):
        self._controller = controller
        self._chunks: list[CodeChunk] = []
        self._symbols: list[SymbolEntry] = []
        self._encoder = None
        try:
            from viki.core.embeddings import get_encoder

            self._encoder = get_encoder()
        except Exception as e:
            viki_logger.debug("code_search: encoder unavailable (%s); using lexical ranking.", e)
        self._index_db: sqlite3.Connection | None = None
        self._index_db_path: str | None = None
        self._open_index_db()
        self._load_from_index()

    def _data_dir(self) -> str:
        if self._controller and hasattr(self._controller, "settings"):
            return cast("str", self._controller.settings.get("system", {}).get("data_dir", "./data"))
        return "./data"

    def _open_index_db(self) -> None:
        try:
            data_dir = self._data_dir()
            os.makedirs(data_dir, exist_ok=True)
            self._index_db_path = os.path.join(data_dir, "code_index.db")
            self._index_db = sqlite3.connect(
                self._index_db_path, check_same_thread=False, timeout=30.0
            )
            self._index_db.execute("PRAGMA journal_mode=WAL")
            self._index_db.row_factory = sqlite3.Row
            self._index_db.executescript(
                """
                CREATE TABLE IF NOT EXISTS files (
                    path TEXT PRIMARY KEY,
                    mtime REAL NOT NULL,
                    size INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    language TEXT,
                    indexed_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    path TEXT NOT NULL,
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    language TEXT,
                    symbol TEXT,
                    text TEXT NOT NULL,
                    embedding TEXT
                );
                CREATE TABLE IF NOT EXISTS symbols (
                    name TEXT NOT NULL,
                    path TEXT NOT NULL,
                    line INTEGER NOT NULL,
                    language TEXT,
                    kind TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path);
                CREATE INDEX IF NOT EXISTS idx_symbols_path ON symbols(path);
                CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
                """
            )
            self._index_db.commit()
        except Exception as e:
            viki_logger.debug(
                "code_search: index DB unavailable (%s); falling back to memory only.", e
            )
            self._index_db = None

    def _load_from_index(self) -> None:
        if self._index_db is None:
            return
        try:
            cur = self._index_db.cursor()
            chunks: list[CodeChunk] = []
            for r in cur.execute(
                "SELECT path, start_line, end_line, language, symbol, text, embedding FROM chunks"
            ):
                emb = None
                if r["embedding"]:
                    try:
                        emb = json.loads(r["embedding"])
                    except Exception:
                        emb = None
                chunks.append(
                    CodeChunk(
                        path=r["path"],
                        start_line=r["start_line"],
                        end_line=r["end_line"],
                        language=r["language"],
                        text=r["text"],
                        symbol=r["symbol"],
                        embedding=emb,
                    )
                )
            self._chunks = chunks
            symbols: list[SymbolEntry] = []
            for r in cur.execute("SELECT name, path, line, language, kind FROM symbols"):
                symbols.append(
                    SymbolEntry(
                        name=r["name"],
                        path=r["path"],
                        line=r["line"],
                        language=r["language"] or "",
                        kind=r["kind"] or "function",
                    )
                )
            self._symbols = symbols
            viki_logger.info(
                "code_search: loaded %d chunks / %d symbols from %s",
                len(chunks),
                len(symbols),
                self._index_db_path,
            )
        except Exception as e:
            viki_logger.debug("code_search: failed to load index: %s", e)

    def invalidate_path(self, path: str) -> None:
        """
        Drop the cached chunks/symbols for `path` and re-index just that file
        on the next query/scan. Designed for a `watchdog` daemon to call on
        file create/modify/delete events.
        """
        if self._index_db is None:
            return
        try:
            cur = self._index_db.cursor()
            cur.execute("DELETE FROM chunks WHERE path = ?", (path,))
            cur.execute("DELETE FROM symbols WHERE path = ?", (path,))
            cur.execute("DELETE FROM files WHERE path = ?", (path,))
            self._index_db.commit()
        except Exception as e:
            viki_logger.debug("code_search: invalidate_path %s failed: %s", path, e)
        # Drop in-memory copies too.
        self._chunks = [c for c in self._chunks if c.path != path]
        self._symbols = [s for s in self._symbols if s.path != path]

    # --- skill metadata ---
    @property
    def name(self) -> str:
        return "code_search"

    @property
    def description(self) -> str:
        return (
            "Repo-aware code search. Usage:\n"
            "- search(query='...', top_k=5)\n"
            "- symbol(name='ClassOrFunction')\n"
            "- scan() to rebuild the index"
        )

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["search", "symbol", "scan", "explain_code"],
                    "description": "Operation to perform.",
                },
                "query": {"type": "string", "description": "Search text or symbol name."},
                "top_k": {"type": "integer", "default": 5},
                "language": {
                    "type": "string",
                    "description": "Optional language filter for symbol search.",
                },
                "path": {"type": "string", "description": "File path for explain_code."},
                "workspace_dir": {
                    "type": "string",
                    "description": "Optional workspace dir override for scan.",
                },
            },
            "required": ["action"],
        }

    # --- public API used by Planner / DevSkill ---
    async def execute(self, params: dict[str, Any]) -> str:
        action = (params.get("action") or "").lower()
        if action == "scan":
            workspace = params.get("workspace_dir") or self._workspace_dir()
            n_files, n_chunks, n_symbols = self.scan(workspace)
            return (
                f"Indexed {n_files} files, {n_chunks} chunks, {n_symbols} symbols from {workspace}."
            )
        if action == "search":
            query = params.get("query") or ""
            top_k = int(params.get("top_k") or 5)
            results = self.search(query, top_k=top_k)
            return json.dumps([r.as_dict() for r in results], indent=2)
        if action == "symbol":
            name = params.get("query") or params.get("name") or ""
            language = params.get("language")
            symbols = self.find_symbol(name, language=language)
            return json.dumps(
                [
                    {
                        "name": s.name,
                        "path": s.path,
                        "line": s.line,
                        "kind": s.kind,
                        "language": s.language,
                    }
                    for s in symbols
                ],
                indent=2,
            )
        if action == "explain_code":
            path = params.get("path")
            if not path:
                return "Error: explain_code requires 'path'."
            return await self._explain_code(path)
        return f"Unknown code_search action '{action}'."

    async def _explain_code(self, path: str) -> str:
        """Use LLM to explain the logic of a file."""
        if not os.path.exists(path):
            # Try workspace relative
            ws = self._workspace_dir()
            path = os.path.join(ws, path)
            if not os.path.exists(path):
                return f"Error: File '{path}' not found."

        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                content = f.read()

            # Truncate if too large for prompt
            if len(content) > 10000:
                content = content[:10000] + "\n... (truncated)"

            model = self._controller.model_router.get_model(["reasoning", "fast_response"])
            prompt = (
                f"Explain the purpose and architectural logic of the following file: {path}\n\n"
                f"```\n{content}\n```\n\n"
                f"Provide a concise summary of main classes, functions, and the overall flow."
            )

            return cast("str", await model.chat([{"role": "user", "content": prompt}]))
        except Exception as e:
            return f"Explain Error: {e}"

    def _workspace_dir(self) -> str:
        if self._controller and hasattr(self._controller, "settings"):
            return cast("str", self._controller.settings.get("system", {}).get("workspace_dir", "./workspace"))
        return os.getcwd()

    # --- index build ---
    def scan(self, workspace_dir: str, incremental: bool = True) -> tuple[int, int, int]:
        """
        Walk `workspace_dir` and refresh the index. When `incremental=True`
        and a SQLite cache exists, only files whose `(mtime, size, sha256)`
        changed are re-indexed; everything else is loaded from cache.
        """
        t0 = time.perf_counter()
        existing: dict[str, tuple[float, int, str]] = {}
        if self._index_db is not None and incremental:
            try:
                cur = self._index_db.cursor()
                for r in cur.execute("SELECT path, mtime, size, sha256 FROM files"):
                    existing[r["path"]] = (float(r["mtime"]), int(r["size"]), r["sha256"])
            except Exception as e:
                viki_logger.debug("code_search: existing-files lookup failed: %s", e)
                existing = {}

        seen_paths: list[str] = []
        n_files_visited = 0
        n_files_reindexed = 0
        new_chunks: list[CodeChunk] = []
        new_symbols: list[SymbolEntry] = []
        new_file_meta: list[tuple[str, float, int, str, str]] = []

        for root, dirs, files in os.walk(workspace_dir):
            dirs[:] = [d for d in dirs if d not in self.IGNORE_DIRS]
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in self.EXTENSIONS:
                    continue
                path = os.path.join(root, fname)
                seen_paths.append(path)
                n_files_visited += 1
                try:
                    st = os.stat(path)
                except Exception:
                    continue
                try:
                    with open(path, encoding="utf-8", errors="ignore") as f:
                        source = f.read()
                except Exception:
                    continue
                if not source.strip():
                    continue
                lang = self.EXTENSIONS[ext]
                sha = hashlib.sha256(source.encode("utf-8", errors="ignore")).hexdigest()
                prev = existing.get(path)
                if prev and prev == (st.st_mtime, st.st_size, sha):
                    # Reuse cached chunks/symbols already loaded into memory.
                    continue
                # File is new or changed: re-chunk from scratch.
                self.invalidate_path(path)
                file_chunks, file_symbols = self._chunk_file(path, source, lang)
                new_chunks.extend(file_chunks)
                new_symbols.extend(file_symbols)
                new_file_meta.append((path, st.st_mtime, st.st_size, sha, lang))
                n_files_reindexed += 1

        # Files removed from disk: drop them.
        if self._index_db is not None and incremental:
            try:
                cur = self._index_db.cursor()
                disk_set = set(seen_paths)
                cached = [r["path"] for r in cur.execute("SELECT path FROM files")]
                for path in cached:
                    if path not in disk_set:
                        self.invalidate_path(path)
            except Exception as e:
                viki_logger.debug("code_search: cleanup pass failed: %s", e)

        if self._encoder:
            self._embed_chunks(new_chunks)

        # Merge into memory + persist.
        self._chunks.extend(new_chunks)
        self._symbols.extend(new_symbols)
        self._persist_chunks(new_chunks, new_symbols, new_file_meta)
        viki_logger.info(
            "code_search: visited %d files, reindexed %d in %.2fs (incremental=%s)",
            n_files_visited,
            n_files_reindexed,
            time.perf_counter() - t0,
            incremental,
        )
        return n_files_visited, len(self._chunks), len(self._symbols)

    def _persist_chunks(
        self,
        chunks: list[CodeChunk],
        symbols: list[SymbolEntry],
        file_meta: list[tuple[str, float, int, str, str]],
    ) -> None:
        if self._index_db is None:
            return
        try:
            cur = self._index_db.cursor()
            for c in chunks:
                cur.execute(
                    "INSERT INTO chunks (path, start_line, end_line, language, symbol, text, embedding) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        c.path,
                        c.start_line,
                        c.end_line,
                        c.language,
                        c.symbol,
                        c.text,
                        json.dumps(c.embedding) if c.embedding else None,
                    ),
                )
            for s in symbols:
                cur.execute(
                    "INSERT INTO symbols (name, path, line, language, kind) VALUES (?, ?, ?, ?, ?)",
                    (s.name, s.path, s.line, s.language, s.kind),
                )
            for path, mtime, size, sha, lang in file_meta:
                cur.execute(
                    "INSERT OR REPLACE INTO files (path, mtime, size, sha256, language, indexed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (path, mtime, size, sha, lang, time.time()),
                )
            self._index_db.commit()
        except Exception as e:
            viki_logger.debug("code_search: persist failed: %s", e)

    def _chunk_file(
        self, path: str, source: str, lang: str
    ) -> tuple[list[CodeChunk], list[SymbolEntry]]:
        # Try tree-sitter first for high-quality symbols.
        res_ts = self._chunk_with_treesitter(path, source, lang)

        # Always generate sliding-window chunks via the regex path to ensure
        # that top-level logic, global variables, and comments are searchable.
        chunks_regex, symbols_regex = self._chunk_with_regex(path, source, lang)

        if res_ts is not None:
            chunks_ts, symbols_ts = res_ts
            # Merge them: tree-sitter gives us precise symbol chunks,
            # regex gives us full-file coverage. Overlap is acceptable for search.
            return chunks_ts + chunks_regex, symbols_ts

        return chunks_regex, symbols_regex

    def _chunk_with_treesitter(
        self, path: str, source: str, lang: str
    ) -> tuple[list[CodeChunk], list[SymbolEntry]] | None:
        try:
            import tree_sitter_languages  # type: ignore

            parser = tree_sitter_languages.get_parser(lang)
            tree = parser.parse(source.encode("utf-8"))
        except Exception:
            return None

        chunks: list[CodeChunk] = []
        symbols: list[SymbolEntry] = []

        def walk(node):
            kind = node.type
            if kind in (
                "function_definition",
                "class_definition",
                "method_definition",
                "function_declaration",
                "class_declaration",
            ):
                start = node.start_point[0] + 1
                end = node.end_point[0] + 1
                # Pull symbol name from first identifier child.
                name = None
                for child in node.children:
                    if child.type in ("identifier", "type_identifier", "name"):
                        name = source[child.start_byte : child.end_byte]
                        break
                lines = source.splitlines()[start - 1 : end]
                text = "\n".join(lines)
                chunks.append(
                    CodeChunk(
                        path=path,
                        start_line=start,
                        end_line=end,
                        language=lang,
                        text=text,
                        symbol=name,
                    )
                )
                if name:
                    symbols.append(
                        SymbolEntry(
                            name=name,
                            path=path,
                            line=start,
                            language=lang,
                            kind="class" if "class" in kind else "function",
                        )
                    )
            for child in node.children:
                walk(child)

        walk(tree.root_node)
        return chunks, symbols

    def _chunk_with_regex(
        self, path: str, source: str, lang: str
    ) -> tuple[list[CodeChunk], list[SymbolEntry]]:
        symbols: list[SymbolEntry] = []
        if lang == "python":
            for m in _PY_DEF_RE.finditer(source):
                line = source.count("\n", 0, m.start()) + 1
                symbols.append(
                    SymbolEntry(
                        name=m.group("name"), path=path, line=line, language=lang, kind="function"
                    )
                )
            for m in _PY_CLASS_RE.finditer(source):
                line = source.count("\n", 0, m.start()) + 1
                symbols.append(
                    SymbolEntry(
                        name=m.group("name"), path=path, line=line, language=lang, kind="class"
                    )
                )
        elif lang in ("javascript", "typescript"):
            for m in _TS_FN_RE.finditer(source):
                line = source.count("\n", 0, m.start()) + 1
                symbols.append(
                    SymbolEntry(
                        name=m.group("name"), path=path, line=line, language=lang, kind="function"
                    )
                )
            for m in _TS_CLASS_RE.finditer(source):
                line = source.count("\n", 0, m.start()) + 1
                symbols.append(
                    SymbolEntry(
                        name=m.group("name"), path=path, line=line, language=lang, kind="class"
                    )
                )

        # Sliding-window chunks for ranking.
        lines = source.splitlines()
        chunks: list[CodeChunk] = []
        i = 0
        while i < len(lines):
            j = min(i + self.MAX_CHUNK_LINES, len(lines))
            text = "\n".join(lines[i:j]).strip()
            if text:
                chunks.append(
                    CodeChunk(
                        path=path,
                        start_line=i + 1,
                        end_line=j,
                        language=lang,
                        text=text,
                    )
                )
            i = j
        return chunks, symbols

    def _embed_chunks(self, chunks: list[CodeChunk]) -> None:
        if not chunks or self._encoder is None:
            return
        try:
            texts = [c.text for c in chunks]
            embs = self._encoder.encode(texts, convert_to_tensor=False)
            for c, e in zip(chunks, embs, strict=False):
                if hasattr(e, "tolist"):
                    c.embedding = e.tolist()
                else:
                    c.embedding = list(e)
        except Exception as exc:
            viki_logger.debug("code_search: embedding pass failed: %s", exc)

    # --- queries ---
    def search(self, query: str, top_k: int = 5) -> list[CodeChunk]:
        if not self._chunks:
            self.scan(self._workspace_dir())
        if not self._chunks:
            return []
        if self._encoder is not None and any(c.embedding for c in self._chunks):
            return self._semantic_rank(query, top_k)
        return self._lexical_rank(query, top_k)

    def _semantic_rank(self, query: str, top_k: int) -> list[CodeChunk]:
        try:
            import numpy as np

            q_emb = self._encoder.encode(query, convert_to_tensor=False)
            q_vec = np.asarray(q_emb, dtype=float)
            q_norm = q_vec / (np.linalg.norm(q_vec) + 1e-9)
            scored: list[tuple[float, CodeChunk]] = []
            for chunk in self._chunks:
                if not chunk.embedding:
                    continue
                v = np.asarray(chunk.embedding, dtype=float)
                v_norm = v / (np.linalg.norm(v) + 1e-9)
                sim = float(np.dot(q_norm, v_norm))
                scored.append((sim, chunk))
            scored.sort(key=lambda x: -x[0])
            return [c for _, c in scored[:top_k]]
        except Exception as e:
            viki_logger.debug("code_search semantic rank failed: %s", e)
            return self._lexical_rank(query, top_k)

    def _lexical_rank(self, query: str, top_k: int) -> list[CodeChunk]:
        q_tokens = {w for w in re.findall(r"\w+", query.lower()) if len(w) > 2}
        scored: list[tuple[float, CodeChunk]] = []
        for chunk in self._chunks:
            tokens = {w for w in re.findall(r"\w+", chunk.text.lower()) if len(w) > 2}
            if not tokens or not q_tokens:
                continue
            inter = len(q_tokens & tokens)
            score = inter / (len(q_tokens) + 1e-6)
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda x: -x[0])
        return [c for _, c in scored[:top_k]]

    def find_symbol(self, name: str, language: str | None = None) -> list[SymbolEntry]:
        if not self._symbols:
            self.scan(self._workspace_dir())
        results = [s for s in self._symbols if s.name == name]
        if language:
            results = [s for s in results if s.language == language]
        return results

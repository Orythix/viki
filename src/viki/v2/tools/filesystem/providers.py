"""Filesystem provider abstraction — blocking I/O offloaded to thread pool."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FileInfo:
    path: str
    name: str
    size: int
    is_dir: bool
    modified: float
    permissions: str


class FSProvider(ABC):
    """Abstract filesystem operations."""

    @abstractmethod
    async def read_file(self, path: str) -> str:
        ...

    @abstractmethod
    async def write_file(self, path: str, content: str) -> bool:
        ...

    @abstractmethod
    async def list_dir(self, path: str) -> list[FileInfo]:
        ...

    @abstractmethod
    async def search_files(self, root: str, pattern: str) -> list[str]:
        ...

    @abstractmethod
    async def exists(self, path: str) -> bool:
        ...

    @abstractmethod
    async def is_dir(self, path: str) -> bool:
        ...

    @abstractmethod
    async def mkdir(self, path: str, parents: bool = True) -> bool:
        ...

    @abstractmethod
    async def remove(self, path: str, recursive: bool = False) -> bool:
        ...

    @abstractmethod
    async def copy(self, src: str, dst: str) -> bool:
        ...

    @abstractmethod
    async def move(self, src: str, dst: str) -> bool:
        ...

    @abstractmethod
    async def get_file_info(self, path: str) -> FileInfo | None:
        ...


class LocalFSProvider(FSProvider):
    """Local filesystem provider — all I/O offloaded to thread pool."""

    def _resolve(self, path: str) -> Path:
        return Path(path).resolve()

    async def read_file(self, path: str) -> str:
        p = self._resolve(path)
        return await asyncio.to_thread(p.read_text, encoding="utf-8", errors="replace")

    async def write_file(self, path: str, content: str) -> bool:
        p = self._resolve(path)

        def _():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return True

        return await asyncio.to_thread(_)

    async def list_dir(self, path: str) -> list[FileInfo]:
        root = self._resolve(path)

        def _():
            if not root.exists():
                return []
            items = []
            for item in root.iterdir():
                stat = item.stat()
                items.append(
                    FileInfo(
                        path=str(item),
                        name=item.name,
                        size=stat.st_size,
                        is_dir=item.is_dir(),
                        modified=stat.st_mtime,
                        permissions=oct(stat.st_mode)[-3:],
                    )
                )
            return items

        return await asyncio.to_thread(_)

    async def search_files(self, root: str, pattern: str) -> list[str]:
        root_path = self._resolve(root)

        def _():
            results = []
            for path in root_path.rglob(pattern):
                if path.is_file():
                    results.append(str(path))
            return results

        return await asyncio.to_thread(_)

    async def exists(self, path: str) -> bool:
        p = self._resolve(path)
        return await asyncio.to_thread(p.exists)

    async def is_dir(self, path: str) -> bool:
        p = self._resolve(path)
        return await asyncio.to_thread(p.is_dir)

    async def mkdir(self, path: str, parents: bool = True) -> bool:
        p = self._resolve(path)

        def _():
            p.mkdir(parents=parents, exist_ok=True)
            return True

        return await asyncio.to_thread(_)

    async def remove(self, path: str, recursive: bool = False) -> bool:
        p = self._resolve(path)

        def _():
            if not p.exists():
                return False
            if p.is_dir():
                import shutil

                shutil.rmtree(p)
            else:
                p.unlink()
            return True

        return await asyncio.to_thread(_)

    async def copy(self, src: str, dst: str) -> bool:
        import shutil

        src_p = self._resolve(src)
        dst_p = self._resolve(dst)

        def _():
            shutil.copy2(src_p, dst_p)
            return True

        return await asyncio.to_thread(_)

    async def move(self, src: str, dst: str) -> bool:
        import shutil

        src_p = self._resolve(src)
        dst_p = self._resolve(dst)

        def _():
            shutil.move(src_p, dst_p)
            return True

        return await asyncio.to_thread(_)

    async def get_file_info(self, path: str) -> FileInfo | None:
        p = self._resolve(path)

        def _():
            if not p.exists():
                return None
            stat = p.stat()
            return FileInfo(
                path=str(p),
                name=p.name,
                size=stat.st_size,
                is_dir=p.is_dir(),
                modified=stat.st_mtime,
                permissions=oct(stat.st_mode)[-3:],
            )

        return await asyncio.to_thread(_)

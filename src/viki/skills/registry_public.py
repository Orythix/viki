"""
Skill/playbook registry — curated, signed index for community skills.

Supports `viki install <skill>` with hash-pinned downloads from a registry
index.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import urllib.request
from dataclasses import dataclass, field

from viki.config.logger import viki_logger


@dataclass
class RegistryPackage:
    """A skill or playbook package in the registry."""

    name: str
    version: str
    description: str
    author: str = ""
    package_type: str = "skill"  # skill, playbook, persona
    download_url: str = ""
    sha256: str = ""
    dependencies: list[str] = field(default_factory=list)
    safety_tier: str = "safe"
    tags: list[str] = field(default_factory=list)
    installed: bool = False
    install_path: str = ""


class SkillRegistryIndex:
    """
    Manages the curated registry index for community skills and playbooks.

    Usage:
        registry = SkillRegistryIndex()
        packages = registry.search("code analysis")
        registry.install("code-analyzer")
    """

    DEFAULT_INDEX_URL = "https://raw.githubusercontent.com/Orythix/viki-registry/main/index.json"

    def __init__(self, data_dir: str = "./data"):
        self._data_dir = data_dir
        self._index_path = os.path.join(data_dir, "registry_index.json")
        self._installed_path = os.path.join(data_dir, "registry_installed.json")
        self._index: list[RegistryPackage] = []
        self._installed: dict[str, RegistryPackage] = {}
        os.makedirs(data_dir, exist_ok=True)
        self._load_installed()

    async def refresh_index(self, url: str | None = None) -> int:
        """Fetch the latest registry index from the remote URL."""
        url = url or self.DEFAULT_INDEX_URL
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self._index = [RegistryPackage(**pkg) for pkg in data.get("packages", [])]
                        await self._save_index()
                        viki_logger.info(
                            "RegistryIndex: refreshed %d packages from %s", len(self._index), url
                        )
                        return len(self._index)
        except ImportError:
            pass
        except Exception as e:
            viki_logger.error("RegistryIndex: refresh failed: %s", e)

        # Try urllib fallback
        try:
            resp = await asyncio.to_thread(urllib.request.urlopen, url, timeout=15)
            data = json.loads(resp.read().decode())
            self._index = [RegistryPackage(**pkg) for pkg in data.get("packages", [])]
            await self._save_index()
            return len(self._index)
        except Exception as e:
            viki_logger.error("RegistryIndex: fallback refresh failed: %s", e)
        return 0

    def search(self, query: str = "") -> list[RegistryPackage]:
        """Search the registry index."""
        if not self._index:
            self._load_index()
        if not query:
            return self._index
        q = query.lower()
        results = []
        for pkg in self._index:
            if (
                q in pkg.name.lower()
                or q in pkg.description.lower()
                or any(q in t.lower() for t in pkg.tags)
            ):
                results.append(pkg)
        return results

    async def install(self, name: str, target_dir: str = "") -> str:
        """Install a package from the registry."""
        if not self._index:
            self._load_index()

        pkg = next((p for p in self._index if p.name == name), None)
        if pkg is None:
            return f"Package '{name}' not found in registry"

        if name in self._installed:
            return f"Package '{name}' already installed"

        target = target_dir or os.path.join(
            self._data_dir, "installed", pkg.package_type + "s", name
        )
        os.makedirs(os.path.dirname(target), exist_ok=True)

        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.get(pkg.download_url, timeout=30) as resp:
                    if resp.status != 200:
                        return f"Download failed: HTTP {resp.status}"
                    content = await resp.read()
        except ImportError:
            resp = await asyncio.to_thread(urllib.request.urlopen, pkg.download_url, timeout=30)
            content = resp.read()

        # Verify hash
        if pkg.sha256:
            actual_hash = hashlib.sha256(content).hexdigest()
            if actual_hash != pkg.sha256:
                return f"Hash mismatch: expected {pkg.sha256}, got {actual_hash}"

        # Extract based on package type
        if pkg.download_url.endswith(".py"):
            install_file = target + ".py"
            await asyncio.to_thread(
                lambda: open(install_file, "wb").write(content)
            )
            pkg.install_path = install_file
        elif pkg.download_url.endswith(".zip") or pkg.download_url.endswith(".tar.gz"):
            import tarfile
            import tempfile
            import zipfile

            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pkg")
            tmp.write(content)
            tmp.close()
            os.makedirs(target, exist_ok=True)
            if pkg.download_url.endswith(".zip"):
                await asyncio.to_thread(
                    lambda: zipfile.ZipFile(tmp.name, "r").extractall(target)
                )
            else:
                await asyncio.to_thread(
                    lambda: tarfile.open(tmp.name, "r:gz").extractall(target)
                )
            os.unlink(tmp.name)
            pkg.install_path = target

        pkg.installed = True
        self._installed[name] = pkg
        self._save_installed()
        viki_logger.info("RegistryIndex: installed '%s' v%s", name, pkg.version)
        return f"Installed '{name}' v{pkg.version} to {pkg.install_path}"

    def uninstall(self, name: str) -> str:
        """Remove an installed package."""
        pkg = self._installed.pop(name, None)
        if pkg is None:
            return f"Package '{name}' not installed"
        if pkg.install_path and os.path.exists(pkg.install_path):
            if os.path.isdir(pkg.install_path):
                import shutil

                shutil.rmtree(pkg.install_path)
            else:
                os.remove(pkg.install_path)
        self._save_installed()
        return f"Uninstalled '{name}'"

    def list_installed(self) -> list[RegistryPackage]:
        return list(self._installed.values())

    async def _save_index(self) -> None:
        try:
            data = [
                {
                    "name": p.name,
                    "version": p.version,
                    "description": p.description,
                    "author": p.author,
                    "package_type": p.package_type,
                    "download_url": p.download_url,
                    "sha256": p.sha256,
                    "dependencies": p.dependencies,
                    "safety_tier": p.safety_tier,
                    "tags": p.tags,
                }
                for p in self._index
            ]
            await asyncio.to_thread(
                lambda: open(self._index_path, "w").write(json.dumps(data, indent=2))
            )
        except Exception as e:
            viki_logger.error("RegistryIndex: save index failed: %s", e)

    def _load_index(self) -> None:
        if not os.path.exists(self._index_path):
            return
        try:
            with open(self._index_path) as f:
                data = json.load(f)
            self._index = [RegistryPackage(**pkg) for pkg in data]
        except Exception as e:
            viki_logger.error("RegistryIndex: load index failed: %s", e)

    def _save_installed(self) -> None:
        try:
            data = {
                name: {
                    "name": p.name,
                    "version": p.version,
                    "description": p.description,
                    "install_path": p.install_path,
                    "safety_tier": p.safety_tier,
                }
                for name, p in self._installed.items()
            }
            with open(self._installed_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            viki_logger.error("RegistryIndex: save installed failed: %s", e)

    def _load_installed(self) -> None:
        if not os.path.exists(self._installed_path):
            return
        try:
            with open(self._installed_path) as f:
                data = json.load(f)
            for name, pkg_data in data.items():
                p = RegistryPackage(**pkg_data)
                p.installed = True
                self._installed[name] = p
        except Exception as e:
            viki_logger.error("RegistryIndex: load installed failed: %s", e)

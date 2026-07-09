"""Cross-platform dependency detection and installation."""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from dataclasses import dataclass

from viki._compat import StrEnum


class DepStatus(StrEnum):
    OK = "ok"
    MISSING = "missing"
    WRONG_VERSION = "wrong_version"
    ERROR = "error"


@dataclass
class DependencyResult:
    name: str
    status: DepStatus
    version: str = ""
    required_version: str = ""
    install_hint: str = ""
    install_command: str = ""
    size_mb: float = 0.0


class DependencyManager:
    """Detect and install system dependencies for VIKI."""

    def __init__(self, interactive: bool = True, mode: str = "light"):
        self.interactive = interactive
        self.mode = mode
        self.results: list[DependencyResult] = []

    async def check_all(self) -> list[DependencyResult]:
        """Run all dependency checks and return results."""
        self.results = []
        self.results.extend(await self._check_python())
        self.results.extend(await self._check_git())
        self.results.extend(await self._check_node())
        self.results.extend(await self._check_cuda())
        self.results.extend(await self._check_vc_redist())
        self.results.extend(await self._check_ollama())
        self.results.extend(await self._check_pip_packages())
        return self.results

    def get_missing(self) -> list[DependencyResult]:
        return [r for r in self.results if r.status != DepStatus.OK]

    async def install_missing(self, confirm_callback=None) -> list[DependencyResult]:
        """Install all missing dependencies with optional confirmation."""
        missing = self.get_missing()
        installed: list[DependencyResult] = []

        for dep in missing:
            if self.interactive and confirm_callback:
                proceed = await confirm_callback(dep)
                if not proceed:
                    continue

            success = await self._install_one(dep)
            if success:
                dep.status = DepStatus.OK
            installed.append(dep)

        return installed

    async def _run(self, cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
        try:
            return await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True, timeout=timeout
            )
        except FileNotFoundError:
            result = subprocess.CompletedProcess(cmd, -1, "", "")
            result.stdout = ""
            result.stderr = "not found"
            return result

    def _version_str(self, result: subprocess.CompletedProcess) -> str:
        return result.stdout.strip().splitlines()[0].strip() if result.stdout.strip() else ""

    async def _check_python(self) -> list[DependencyResult]:
        results = []
        version = sys.version.split()[0]
        major, minor, *_ = (int(x) for x in version.split("."))
        ok = major >= 3 and minor >= 11
        results.append(
            DependencyResult(
                name="Python",
                status=DepStatus.OK if ok else DepStatus.WRONG_VERSION,
                version=version,
                required_version=">=3.11",
                install_hint="https://python.org/downloads/",
                install_command="",
            )
        )
        # pip
        pip_result = await self._run([sys.executable, "-m", "pip", "--version"])
        pip_ok = pip_result.returncode == 0
        results.append(
            DependencyResult(
                name="pip",
                status=DepStatus.OK if pip_ok else DepStatus.MISSING,
                version=self._version_str(pip_result).split()[1] if pip_ok else "",
                required_version="latest",
                install_command=f'"{sys.executable}" -m ensurepip --upgrade',
            )
        )
        return results

    async def _check_git(self) -> list[DependencyResult]:
        if self.mode == "light":
            return []
        result = await self._run(["git", "--version"])
        ok = result.returncode == 0
        return [
            DependencyResult(
                name="Git",
                status=DepStatus.OK if ok else DepStatus.MISSING,
                version=self._version_str(result).replace("git version ", "") if ok else "",
                required_version="latest",
                install_hint="https://git-scm.com/downloads",
                install_command="winget install Git.Git"
                if sys.platform == "win32"
                else "apt install git"
                if sys.platform == "linux"
                else "brew install git",
                size_mb=50.0,
            )
        ]

    async def _check_node(self) -> list[DependencyResult]:
        if self.mode == "light":
            return []
        result = await self._run(["node", "--version"])
        ok = result.returncode == 0
        return [
            DependencyResult(
                name="Node.js",
                status=DepStatus.OK if ok else DepStatus.MISSING,
                version=self._version_str(result) if ok else "",
                required_version=">=18",
                install_hint="https://nodejs.org/",
                install_command="winget install OpenJS.NodeJS.LTS"
                if sys.platform == "win32"
                else "apt install nodejs"
                if sys.platform == "linux"
                else "brew install node",
                size_mb=40.0,
            )
        ]

    async def _check_cuda(self) -> list[DependencyResult]:
        """Check for CUDA toolkit and NVIDIA driver."""
        results = []

        # nvidia-smi check
        nv_result = await self._run(["nvidia-smi"], timeout=10)
        has_nvidia = nv_result.returncode == 0
        driver_version = ""
        cuda_version = ""
        if has_nvidia:
            for line in nv_result.stdout.splitlines():
                if "Driver Version" in line:
                    parts = line.strip().split()
                    for p in parts:
                        if "." in p and p[0].isdigit():
                            driver_version = p
                            break
                if "CUDA Version" in line:
                    parts = line.strip().split()
                    for i, p in enumerate(parts):
                        if p == "Version" and i + 1 < len(parts):
                            cuda_version = parts[i + 1].rstrip(".")
                            break

        results.append(
            DependencyResult(
                name="NVIDIA Driver",
                status=DepStatus.OK if has_nvidia else DepStatus.MISSING,
                version=driver_version,
                required_version=">=525",
                install_hint="https://nvidia.com/drivers",
                size_mb=800.0,
            )
        )

        # CUDA toolkit (for finetuning)
        if self.mode == "advanced" and has_nvidia:
            nvcc_result = await self._run(["nvcc", "--version"])
            has_nvcc = nvcc_result.returncode == 0
            results.append(
                DependencyResult(
                    name="CUDA Toolkit",
                    status=DepStatus.OK if has_nvcc else DepStatus.MISSING,
                    version=self._version_str(nvcc_result).split()[-1]
                    if has_nvcc
                    else cuda_version,
                    required_version=">=12.1",
                    install_hint="https://developer.nvidia.com/cuda-downloads",
                    install_command="winget install NVIDIA.CUDA"
                    if sys.platform == "win32"
                    else "apt install nvidia-cuda-toolkit",
                    size_mb=2500.0,
                )
            )

        return results

    async def _check_vc_redist(self) -> list[DependencyResult]:
        """Check for Visual C++ Redistributable (Windows only)."""
        if sys.platform != "win32":
            return []

        # Quick check: look for vcruntime140.dll
        vc_ok = False
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["where", "vcruntime140.dll"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            vc_ok = result.returncode == 0
        except Exception:
            logging.getLogger(__name__).warning("vc_redist check failed")

        return [
            DependencyResult(
                name="Visual C++ Runtime",
                status=DepStatus.OK if vc_ok else DepStatus.MISSING,
                version="",
                required_version="2015-2022",
                install_hint="https://aka.ms/vs/17/release/vc_redist.x64.exe",
                install_command="winget install Microsoft.VCRedist.2015+.x64",
                size_mb=25.0,
            )
        ]

    async def _check_ollama(self) -> list[DependencyResult]:
        """Check if Ollama is installed."""
        result = await self._run(["ollama", "--version"])
        ok = result.returncode == 0
        return [
            DependencyResult(
                name="Ollama",
                status=DepStatus.OK if ok else DepStatus.MISSING,
                version=self._version_str(result).replace("ollama version ", "") if ok else "",
                required_version="latest",
                install_hint="https://ollama.com/download",
                install_command="winget install Ollama.Ollama"
                if sys.platform == "win32"
                else "curl -fsSL https://ollama.com/install.sh | sh",
                size_mb=800.0,
            )
        ]

    async def _check_pip_packages(self) -> list[DependencyResult]:
        """Check core Python packages."""
        core_packages = [
            ("rich", ">=13.7"),
            ("pydantic", ">=2.5"),
            ("aiohttp", ">=3.9"),
            ("pyyaml", ">=6.0"),
            ("python-dotenv", ">=1.0"),
            ("cryptography", ">=41.0"),
        ]

        results = []
        for pkg, ver_req in core_packages:
            try:
                result = await self._run([sys.executable, "-m", "pip", "show", pkg])
                if result.returncode == 0:
                    version = ""
                    for line in result.stdout.splitlines():
                        if line.startswith("Version:"):
                            version = line.split(":", 1)[1].strip()
                            break
                    results.append(
                        DependencyResult(
                            name=pkg,
                            status=DepStatus.OK,
                            version=version,
                            required_version=ver_req,
                        )
                    )
                else:
                    results.append(
                        DependencyResult(
                            name=pkg,
                            status=DepStatus.MISSING,
                            version="",
                            required_version=ver_req,
                            install_command=f'"{sys.executable}" -m pip install "{pkg}{ver_req}"',
                            size_mb=0.5,
                        )
                    )
            except Exception:
                results.append(
                    DependencyResult(
                        name=pkg,
                        status=DepStatus.ERROR,
                        version="",
                        required_version=ver_req,
                    )
                )

        return results

    async def _install_one(self, dep: DependencyResult) -> bool:
        """Install a single dependency."""
        if not dep.install_command:
            print(
                f"  [yellow]No auto-install available for {dep.name}. Please install manually: {dep.install_hint}"
            )
            return False

        print(f"  Installing {dep.name}...")
        try:
            if dep.name == "Ollama":
                return await self._install_ollama()
            elif dep.install_command.startswith("pip"):
                result = await self._run(dep.install_command.split(), timeout=120)
                return result.returncode == 0
            elif dep.install_command.startswith("winget"):
                result = await self._run(dep.install_command.split(), timeout=120)
                return result.returncode == 0
            elif dep.install_command.startswith(("apt", "brew")):
                result = await self._run(dep.install_command.split(), timeout=120)
                return result.returncode == 0
            else:
                print(f"  Auto-install not implemented: {dep.install_command}")
                return False
        except subprocess.TimeoutExpired:
            print(f"  [red]Installation of {dep.name} timed out.[/]")
            return False
        except Exception as e:
            print(f"  [red]Failed to install {dep.name}: {e}[/]")
            return False

    async def _install_ollama(self) -> bool:
        """Install Ollama based on platform."""
        if sys.platform == "win32":
            try:
                await asyncio.to_thread(
                    subprocess.run,
                    [
                        "powershell",
                        "-Command",
                        "Invoke-WebRequest -Uri https://ollama.com/download/OllamaSetup.exe -OutFile $env:TEMP\\OllamaSetup.exe",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                result = await asyncio.to_thread(
                    subprocess.run,
                    ["$env:TEMP\\OllamaSetup.exe", "/S"],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                return result.returncode == 0
            except Exception as e:
                print(f"  [red]Ollama install failed: {e}[/]")
                return False
        else:
            # Linux/macOS — use the official install script
            try:
                result = await asyncio.to_thread(
                    subprocess.run,
                    ["sh", "-c", "curl -fsSL https://ollama.com/install.sh | sh"],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                return result.returncode == 0
            except Exception as e:
                print(f"  [red]Ollama install failed: {e}[/]")
                return False

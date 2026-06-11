"""Cross-platform system detection — OS, CPU, RAM, GPU, storage."""

from __future__ import annotations

import os
import platform
import re
import subprocess
import sys
from dataclasses import dataclass, field
from enum import StrEnum


class OSType(StrEnum):
    WINDOWS = "windows"
    LINUX = "linux"
    MACOS = "macos"
    UNKNOWN = "unknown"


class GPUVendor(StrEnum):
    NVIDIA = "nvidia"
    AMD = "amd"
    INTEL = "intel"
    APPLE = "apple"
    UNKNOWN = "unknown"


class InstallMode(StrEnum):
    LIGHT = "light"
    DEVELOPER = "developer"
    ADVANCED = "advanced"


@dataclass
class GPUInfo:
    model: str = ""
    vendor: GPUVendor = GPUVendor.UNKNOWN
    vram_mb: int = 0
    cuda_cores: int = 0
    compute_capability: str = ""


@dataclass
class SystemInfo:
    os_type: OSType = OSType.UNKNOWN
    os_name: str = ""
    os_version: str = ""
    cpu_model: str = ""
    cpu_cores: int = 0
    cpu_threads: int = 0
    ram_mb: int = 0
    storage_free_mb: int = 0
    storage_total_mb: int = 0
    gpus: list[GPUInfo] = field(default_factory=list)
    python_version: str = ""
    is_admin: bool = False
    is_container: bool = False
    is_wsl: bool = False


@dataclass
class HardwareProfile:
    """Hardware-based profile for model/dependency recommendations."""

    tier: str = "cpu"  # cpu, low_gpu, mid_gpu, high_gpu, apple
    ram_tier: str = "medium"  # low (<8GB), medium (8-16GB), high (16-32GB), ultra (>32GB)
    vram_tier: str = "none"  # none, low (<4GB), medium (4-8GB), high (8-16GB), ultra (>16GB)
    recommended_mode: InstallMode = InstallMode.LIGHT
    can_run_14b: bool = False
    can_run_30b: bool = False
    can_run_70b: bool = False
    can_finetune: bool = False


def _detect_os() -> tuple[OSType, str, str]:
    system = platform.system().lower()
    if system == "windows":
        return OSType.WINDOWS, f"Windows {platform.version()}", platform.version()
    elif system == "linux":
        os_name = "Linux"
        os_version = platform.release()
        # Try to get distro info
        for path in ("/etc/os-release", "/etc/lsb-release"):
            try:
                with open(path) as f:
                    content = f.read()
                    for line in content.splitlines():
                        if line.startswith("PRETTY_NAME="):
                            os_name = line.split("=", 1)[1].strip('"')
                        elif line.startswith("VERSION_ID="):
                            os_version = line.split("=", 1)[1].strip('"')
            except OSError:
                pass
        return OSType.LINUX, os_name, os_version
    elif system == "darwin":
        return OSType.MACOS, f"macOS {platform.mac_ver()[0]}", platform.mac_ver()[0]
    return OSType.UNKNOWN, platform.system(), ""


def _detect_cpu() -> tuple[str, int, int]:
    cpu_model = "Unknown"
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["wmic", "cpu", "get", "name", "/format:list"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in result.stdout.splitlines():
                if line.startswith("Name="):
                    cpu_model = line.split("=", 1)[1].strip()
                    break
        elif sys.platform == "linux":
            try:
                with open("/proc/cpuinfo") as f:
                    for line in f:
                        if line.startswith("model name"):
                            cpu_model = line.split(":", 1)[1].strip()
                            break
            except OSError:
                pass
        elif sys.platform == "darwin":
            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            cpu_model = result.stdout.strip()
    except Exception:
        pass

    cores = os.cpu_count() or 0
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["wmic", "cpu", "get", "NumberOfLogicalProcessors", "/format:list"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in result.stdout.splitlines():
                if line.startswith("NumberOfLogicalProcessors="):
                    threads = int(line.split("=", 1)[1].strip())
                    return cpu_model, cores, threads
        elif sys.platform == "linux":
            try:
                with open("/proc/cpuinfo") as f:
                    threads = sum(1 for line in f if line.startswith("processor"))
                    return cpu_model, cores, threads
            except OSError:
                pass
    except Exception:
        pass
    return cpu_model, cores, cores


def _detect_ram() -> int:
    """Return total RAM in MB."""
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["wmic", "computersystem", "get", "TotalPhysicalMemory", "/format:list"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in result.stdout.splitlines():
                if line.startswith("TotalPhysicalMemory="):
                    return int(line.split("=", 1)[1].strip()) // (1024 * 1024)
        elif sys.platform == "linux":
            try:
                with open("/proc/meminfo") as f:
                    for line in f:
                        if line.startswith("MemTotal:"):
                            kb = int(line.split()[1])
                            return kb // 1024
            except OSError:
                pass
        elif sys.platform == "darwin":
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.stdout.strip():
                return int(result.stdout.strip()) // (1024 * 1024)
    except Exception:
        pass
    # Fallback: try psutil
    try:
        import psutil

        return psutil.virtual_memory().total // (1024 * 1024)
    except ImportError:
        pass
    return 0


def _detect_storage() -> tuple[int, int]:
    """Return (free_mb, total_mb) for the VIKI data directory or current drive."""
    try:
        path = os.environ.get("VIKI_DATA_DIR") or os.getcwd()
        if sys.platform == "win32":
            import ctypes

            drive = os.path.splitdrive(path)[0] + "\\"
            free_bytes = ctypes.c_ulonglong(0)
            total_bytes = ctypes.c_ulonglong(0)
            ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                drive, None, ctypes.byref(total_bytes), ctypes.byref(free_bytes)
            )
            return free_bytes.value // (1024 * 1024), total_bytes.value // (1024 * 1024)
        else:
            stat = os.statvfs(path)
            free = stat.f_frsize * stat.f_bavail // (1024 * 1024)
            total = stat.f_frsize * stat.f_blocks // (1024 * 1024)
            return free, total
    except Exception:
        pass
    try:
        import shutil

        total, used, free = shutil.disk_usage(os.getcwd())
        return free // (1024 * 1024), total // (1024 * 1024)
    except Exception:
        return 0, 0


def _detect_gpu() -> list[GPUInfo]:
    """Detect available GPUs using various methods."""
    gpus: list[GPUInfo] = []

    # Method 1: nvidia-smi
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,compute_cap", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 2:
                    vram_str = parts[1].replace("MiB", "").replace("MB", "").strip()
                    try:
                        vram = int(vram_str)
                    except ValueError:
                        vram = 0
                    gpu = GPUInfo(
                        model=parts[0],
                        vendor=GPUVendor.NVIDIA,
                        vram_mb=vram,
                        compute_capability=parts[2] if len(parts) > 2 else "",
                    )
                    # Estimate CUDA cores from model name
                    gpu.cuda_cores = _estimate_cuda_cores(parts[0])
                    gpus.append(gpu)
            if gpus:
                return gpus
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        pass

    # Method 2: torch
    try:
        import torch

        if torch.cuda.is_available():
            for i in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(i)
                gpus.append(
                    GPUInfo(
                        model=props.name,
                        vendor=GPUVendor.NVIDIA,
                        vram_mb=props.total_memory // (1024 * 1024),
                        cuda_cores=props.multi_processor_count * 128
                        if props.major >= 8
                        else props.multi_processor_count * 64,
                        compute_capability=f"{props.major}.{props.minor}",
                    )
                )
            if gpus:
                return gpus
    except (ImportError, Exception):
        pass

    # Method 3: Windows WMI
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["wmic", "path", "win32_VideoController", "get", "name,adapterram", "/format:list"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            current_name = ""
            current_vram = 0
            for line in result.stdout.splitlines():
                if line.startswith("Name="):
                    current_name = line.split("=", 1)[1].strip()
                elif line.startswith("AdapterRAM="):
                    try:
                        current_vram = int(line.split("=", 1)[1].strip()) // (1024 * 1024)
                    except (ValueError, IndexError):
                        current_vram = 0
                    if current_name:
                        vendor = GPUVendor.UNKNOWN
                        if "nvidia" in current_name.lower():
                            vendor = GPUVendor.NVIDIA
                        elif "amd" in current_name.lower() or "radeon" in current_name.lower():
                            vendor = GPUVendor.AMD
                        elif "intel" in current_name.lower():
                            vendor = GPUVendor.INTEL
                        gpus.append(
                            GPUInfo(model=current_name, vendor=vendor, vram_mb=current_vram)
                        )
                        current_name = ""
            if gpus:
                return gpus
        except Exception:
            pass

    # Method 4: Linux lspci
    if sys.platform == "linux":
        try:
            result = subprocess.run(
                ["lspci", "-v"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            for line in result.stdout.splitlines():
                if "VGA" in line or "3D" in line or "Display" in line:
                    gpu_name = line.split(":", 2)[-1].strip() if ":" in line else line.strip()
                    vendor = GPUVendor.UNKNOWN
                    if "nvidia" in gpu_name.lower():
                        vendor = GPUVendor.NVIDIA
                    elif "amd" in gpu_name.lower() or "radeon" in gpu_name.lower():
                        vendor = GPUVendor.AMD
                    elif "intel" in gpu_name.lower():
                        vendor = GPUVendor.INTEL
                    gpus.append(GPUInfo(model=gpu_name, vendor=vendor))
        except Exception:
            pass

    # Method 5: macOS
    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            for line in result.stdout.splitlines():
                stripped = line.strip()
                if stripped.startswith("Chipset Model:"):
                    model = stripped.split(":", 1)[1].strip()
                    gpus.append(GPUInfo(model=model, vendor=GPUVendor.APPLE))
                elif stripped.startswith("VRAM ("):
                    match = re.search(r"(\d+)\s*(MB|GB)", stripped)
                    if match and gpus:
                        value = int(match.group(1))
                        unit = match.group(2)
                        gpus[-1].vram_mb = value * 1024 if unit == "GB" else value
            if gpus:
                return gpus
        except Exception:
            pass

    return gpus


def _estimate_cuda_cores(model_name: str) -> int:
    """Rough CUDA core estimation from GPU model name."""
    name = model_name.lower()
    if "rtx 4090" in name:
        return 16384
    if "rtx 4080" in name:
        return 9728
    if "rtx 4070" in name:
        return 5888
    if "rtx 4060" in name:
        return 3072
    if "rtx 3090" in name:
        return 10496
    if "rtx 3080" in name:
        return 8704
    if "rtx 3070" in name:
        return 5888
    if "rtx 3060" in name:
        return 3584
    if "rtx 3050" in name:
        return 2560
    if "rtx 2080" in name:
        return 4352
    if "rtx 2070" in name:
        return 2304
    if "rtx 2060" in name:
        return 1920
    return 0


def _check_admin() -> bool:
    """Check if running with admin/root privileges."""
    try:
        if sys.platform == "win32":
            import ctypes

            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        else:
            return os.geteuid() == 0
    except Exception:
        return False


def _check_container() -> bool:
    """Detect if running inside a container."""
    if sys.platform != "linux":
        return False
    try:
        with open("/proc/1/cgroup") as f:
            content = f.read()
            if any(s in content for s in ("docker", "kube", "containerd")):
                return True
    except OSError:
        pass
    try:
        if os.path.exists("/.dockerenv"):
            return True
    except Exception:
        pass
    return False


def _recommend_hardware_profile(info: SystemInfo) -> HardwareProfile:
    """Generate a hardware profile for model/dependency recommendations."""
    profile = HardwareProfile()

    # RAM tier
    ram_gb = info.ram_mb / 1024
    if ram_gb < 8:
        profile.ram_tier = "low"
    elif ram_gb < 16:
        profile.ram_tier = "medium"
    elif ram_gb < 32:
        profile.ram_tier = "high"
    else:
        profile.ram_tier = "ultra"

    # GPU tier
    primary_gpu = info.gpus[0] if info.gpus else None
    if primary_gpu:
        vram_gb = primary_gpu.vram_mb / 1024
        if vram_gb < 4:
            profile.vram_tier = "low"
            profile.tier = "low_gpu"
        elif vram_gb < 8:
            profile.vram_tier = "medium"
            profile.tier = "mid_gpu"
        elif vram_gb < 16:
            profile.vram_tier = "high"
            profile.tier = "high_gpu"
            profile.can_run_14b = True
        else:
            profile.vram_tier = "ultra"
            profile.tier = "high_gpu"
            profile.can_run_14b = True
            profile.can_run_30b = vram_gb >= 20
            profile.can_run_70b = vram_gb >= 40
    elif info.os_type == OSType.MACOS:
        profile.tier = "apple"
        # Apple Silicon has unified memory
        if info.ram_mb / 1024 >= 16:
            profile.can_run_14b = True

    # Finetuning capability
    profile.can_finetune = (
        profile.vram_tier in ("high", "ultra")
        and primary_gpu
        and primary_gpu.vendor == GPUVendor.NVIDIA
    )

    # Recommended install mode
    if profile.ram_tier == "low" or profile.tier == "cpu":
        profile.recommended_mode = InstallMode.LIGHT
    elif profile.ram_tier in ("medium", "high") and profile.tier in ("mid_gpu", "high_gpu"):
        profile.recommended_mode = InstallMode.DEVELOPER
    else:
        profile.recommended_mode = InstallMode.ADVANCED

    return profile


class SystemDetector:
    """Detect system hardware, OS, and compute capabilities."""

    def __init__(self):
        self._info: SystemInfo | None = None
        self._profile: HardwareProfile | None = None

    async def detect(self) -> SystemInfo:
        """Run all detection and return SystemInfo."""
        os_type, os_name, os_version = _detect_os()
        cpu_model, cores, threads = _detect_cpu()
        ram_mb = _detect_ram()
        free_mb, total_mb = _detect_storage()
        gpus = _detect_gpu()

        self._info = SystemInfo(
            os_type=os_type,
            os_name=os_name,
            os_version=os_version,
            cpu_model=cpu_model,
            cpu_cores=cores,
            cpu_threads=threads,
            ram_mb=ram_mb,
            storage_free_mb=free_mb,
            storage_total_mb=total_mb,
            gpus=gpus,
            python_version=platform.python_version(),
            is_admin=_check_admin(),
            is_container=_check_container(),
            is_wsl=os_type == OSType.LINUX and "microsoft" in platform.uname().release.lower(),
        )
        self._profile = _recommend_hardware_profile(self._info)
        return self._info

    def get_profile(self) -> HardwareProfile:
        if self._profile is None:
            raise RuntimeError("Must call detect() first")
        return self._profile

    def format_report(self, info: SystemInfo | None = None) -> str:
        """Format system info as a human-readable report."""
        info = info or self._info
        if info is None:
            return "No system info available."

        lines = [
            f"OS:        {info.os_name} ({info.os_version})",
            f"CPU:       {info.cpu_model} ({info.cpu_cores}C/{info.cpu_threads}T)",
            f"RAM:       {info.ram_mb / 1024:.1f} GB",
            f"Storage:   {info.storage_free_mb / 1024:.1f} GB free / {info.storage_total_mb / 1024:.1f} GB total",
        ]
        if info.gpus:
            for i, gpu in enumerate(info.gpus):
                lines.append(f"GPU {i}:    {gpu.model} ({gpu.vram_mb} MB VRAM)")
        else:
            lines.append("GPU:       None detected (CPU mode)")

        lines.append(f"Python:    {info.python_version}")
        lines.append(f"Admin:     {'Yes' if info.is_admin else 'No'}")
        lines.append(f"Container: {'Yes' if info.is_container else 'No'}")
        lines.append(f"WSL:       {'Yes' if info.is_wsl else 'No'}")

        profile = self._profile
        if profile:
            lines.extend(
                [
                    "",
                    f"Tier:      {profile.tier}",
                    f"Mode:      {profile.recommended_mode.value}",
                    f"14B:       {'Yes' if profile.can_run_14b else 'No'}",
                    f"30B:       {'Yes' if profile.can_run_30b else 'No'}",
                    f"70B:       {'Yes' if profile.can_run_70b else 'No'}",
                    f"Finetune:  {'Yes' if profile.can_finetune else 'No'}",
                ]
            )

        return "\n".join(lines)

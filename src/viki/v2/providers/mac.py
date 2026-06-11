"""macOS provider implementation."""

from __future__ import annotations

import asyncio
import logging
import re

from .base import ShellResult, SystemProvider

logger = logging.getLogger(__name__)


class MacProvider(SystemProvider):
    PLATFORM = "macos"

    async def _run(self, cmd: list[str]) -> ShellResult:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return ShellResult(
            returncode=proc.returncode or 0,
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
        )

    async def get_os_info(self) -> dict:
        r = await self._run(["sw_vers"])
        info = {}
        for line in r.stdout.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                info[k.strip()] = v.strip()
        return info

    async def get_hardware_info(self) -> dict:
        r = await self._run(["sysctl", "-n", "hw.machine"])
        return {"architecture": r.stdout.strip()}

    async def get_cpu_info(self) -> dict:
        r = await self._run(["sysctl", "-n", "machdep.cpu.brand_string"])
        cores = await self._run(["sysctl", "-n", "hw.ncpu"])
        return {"name": r.stdout.strip(), "cores": cores.stdout.strip()}

    async def get_ram_info(self) -> dict:
        r = await self._run(["sysctl", "-n", "hw.memsize"])
        total_gb = round(int(r.stdout.strip()) / (1024**3), 2)
        return {"total_gb": total_gb}

    async def get_disk_info(self) -> list[dict]:
        r = await self._run(["df", "-h"])
        disks = []
        for line in r.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 6:
                disks.append(
                    {
                        "filesystem": parts[0],
                        "size": parts[1],
                        "used": parts[2],
                        "avail": parts[3],
                        "use_percent": parts[4],
                        "mount": parts[5],
                    }
                )
        return disks

    async def get_running_processes(self) -> list[dict]:
        r = await self._run(["ps", "aux", "--sort=-%mem"])
        procs = []
        for line in r.stdout.splitlines()[1:51]:
            parts = line.split(None, 10)
            if len(parts) >= 11:
                procs.append(
                    {
                        "user": parts[0],
                        "pid": parts[1],
                        "cpu": parts[2],
                        "mem": parts[3],
                        "command": parts[10],
                    }
                )
        return procs

    async def get_installed_software(self) -> list[dict]:
        r = await self._run(["ls", "/Applications"])
        apps = [
            {"name": a.replace(".app", "")} for a in r.stdout.splitlines() if a.endswith(".app")
        ]
        return apps

    async def get_wifi_password(self, ssid: str | None = None) -> dict:
        if not ssid:
            r = await self._run(
                [
                    "/System/Library/PrivateFrameworks/Apple80211.framework/"
                    "Versions/Current/Resources/airport",
                    "-I",
                ]
            )
            for line in r.stdout.splitlines():
                m = re.match(r"\s*SSID:\s+(.+)", line)
                if m:
                    ssid = m.group(1).strip()
                    break
        if not ssid:
            return {"error": "Not connected to any Wi-Fi network"}
        r = await self._run(["security", "find-generic-password", "-wa", ssid])
        if r.returncode == 0:
            return {"ssid": ssid, "password": r.stdout.strip()}
        return {"ssid": ssid, "error": "Could not retrieve password"}

    async def get_ip_address(self) -> dict:
        r = await self._run(["ipconfig", "getifaddr", "en0"])
        return {"interfaces": [{"name": "en0", "ip_address": r.stdout.strip()}]}

    async def ping(self, host: str) -> dict:
        r = await self._run(["ping", "-c", "4", host])
        times = re.findall(r"time=(\d+\.?\d*)", r.stdout)
        return {"host": host, "results": [{"response_time": float(t)} for t in times]}

    async def get_network_info(self) -> dict:
        r = await self._run(["networksetup", "-listallhardwareports"])
        return {"raw": r.stdout}

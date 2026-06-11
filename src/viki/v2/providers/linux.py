"""Linux provider implementation."""

from __future__ import annotations

import asyncio
import logging
import re

from .base import ShellResult, SystemProvider

logger = logging.getLogger(__name__)


class LinuxProvider(SystemProvider):
    PLATFORM = "linux"

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
        r = await self._run(["cat", "/etc/os-release"])
        info = {}
        for line in r.stdout.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                info[k] = v.strip('"')
        return info

    async def get_hardware_info(self) -> dict:
        r = await self._run(["uname", "-m"])
        return {"architecture": r.stdout.strip()}

    async def get_cpu_info(self) -> dict:
        r = await self._run(["lscpu"])
        info = {}
        for line in r.stdout.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                info[k.strip()] = v.strip()
        return info

    async def get_ram_info(self) -> dict:
        r = await self._run(["free", "-h"])
        lines = r.stdout.splitlines()
        if len(lines) >= 2:
            parts = lines[1].split()
            return {"total": parts[1], "used": parts[2], "free": parts[3]}
        return {}

    async def get_disk_info(self) -> list[dict]:
        r = await self._run(["df", "-h", "--type=ext4", "--type=xfs", "--type=btrfs"])
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
        r = await self._run(["dpkg", "--list"])
        pkgs = []
        for line in r.stdout.splitlines():
            if line.startswith("ii "):
                parts = line.split(None, 3)
                if len(parts) >= 3:
                    pkgs.append({"name": parts[1], "version": parts[2]})
        return pkgs[:100]

    async def get_wifi_password(self, ssid: str | None = None) -> dict:
        path = f"/etc/NetworkManager/system-connections/{ssid}"
        if ssid:
            r = await self._run(["cat", path])
            for line in r.stdout.splitlines():
                if "psk=" in line:
                    return {"ssid": ssid, "password": line.split("=", 1)[1].strip()}
            return {"ssid": ssid, "password": "No password found"}
        r = await self._run(["iwgetid", "-r"])
        current = r.stdout.strip()
        if current:
            return await self.get_wifi_password(current)
        return {"error": "Not connected to any Wi-Fi network"}

    async def get_ip_address(self) -> dict:
        r = await self._run(["hostname", "-I"])
        ips = r.stdout.strip().split()
        return {"interfaces": [{"ip_address": ip} for ip in ips]}

    async def ping(self, host: str) -> dict:
        r = await self._run(["ping", "-c", "4", host])
        times = re.findall(r"time=(\d+\.?\d*)", r.stdout)
        return {"host": host, "results": [{"response_time": float(t)} for t in times]}

    async def get_network_info(self) -> dict:
        r = await self._run(["ip", "addr"])
        return {"raw": r.stdout}

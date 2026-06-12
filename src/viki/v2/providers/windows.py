"""Windows provider implementation."""

from __future__ import annotations

import asyncio
import json
import logging

from .base import SystemProvider

logger = logging.getLogger(__name__)


class WindowsProvider(SystemProvider):
    PLATFORM = "windows"

    async def _run_powershell(self, command: str, timeout: int = 30) -> str:
        proc = await asyncio.create_subprocess_exec(
            "powershell",
            "-NoProfile",
            "-Command",
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            proc.kill()
            raise RuntimeError(
                f"PowerShell command timed out after {timeout}s: {command[:100]}"
            ) from None
        if proc.returncode != 0:
            raise RuntimeError(stderr.decode("cp1252", errors="replace"))
        return stdout.decode("cp1252", errors="replace")

    async def get_os_info(self) -> dict:
        out = await self._run_powershell(
            "Get-ComputerInfo | Select-Object WindowsVersion, "
            "WindowsEditionId, WindowsInstallationType, OsName, OsVersion | ConvertTo-Json"
        )
        return json.loads(out)

    async def get_hardware_info(self) -> dict:
        out = await self._run_powershell(
            "Get-CimInstance Win32_ComputerSystem | Select-Object Manufacturer, Model, "
            "TotalPhysicalMemory, NumberOfProcessors | ConvertTo-Json"
        )
        return json.loads(out)

    async def get_cpu_info(self) -> dict:
        out = await self._run_powershell(
            "Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, "
            "NumberOfLogicalProcessors, MaxClockSpeed | ConvertTo-Json"
        )
        data = json.loads(out)
        if isinstance(data, list):
            return data[0]
        return data

    async def get_ram_info(self) -> dict:
        out = await self._run_powershell(
            "Get-CimInstance Win32_ComputerSystem | Select-Object @{Name='TotalGB';"
            "Expression={[math]::Round($_.TotalPhysicalMemory/1GB,2)}} | ConvertTo-Json"
        )
        data = json.loads(out)
        if isinstance(data, list):
            data = data[0]
        free = await self._run_powershell(
            "Get-CimInstance Win32_OperatingSystem | Select-Object @{Name='FreeGB';"
            "Expression={[math]::Round($_.FreePhysicalMemory/1MB,2)}} | ConvertTo-Json"
        )
        free_data = json.loads(free)
        if isinstance(free_data, list):
            free_data = free_data[0]
        data["FreeGB"] = free_data.get("FreeGB", 0)
        return data

    async def get_disk_info(self) -> list[dict]:
        out = await self._run_powershell(
            "Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | Select-Object "
            "DeviceID, @{Name='SizeGB';Expression={[math]::Round($_.Size/1GB,2)}}, "
            "@{Name='FreeGB';Expression={[math]::Round($_.FreeSpace/1GB,2)}} | ConvertTo-Json"
        )
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        return data

    async def get_running_processes(self) -> list[dict]:
        out = await self._run_powershell(
            "Get-Process | Select-Object Name, Id, CPU, WorkingSet64, StartTime | "
            "Sort-Object WorkingSet64 -Descending | Select-Object -First 50 | ConvertTo-Json"
        )
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        return data

    async def get_installed_software(self) -> list[dict]:
        out = await self._run_powershell(
            "Get-ItemProperty 'HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*' | "
            "Select-Object DisplayName, DisplayVersion, Publisher, InstallDate | "
            "Where-Object { $_.DisplayName } | ConvertTo-Json -Depth 1"
        )
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        return data

    async def get_wifi_password(self, ssid: str | None = None) -> dict:
        if not ssid:
            out = await self._run_powershell(
                "(netsh wlan show interfaces | Select-String 'SSID' | "
                "Select-String -NotMatch 'BSSID' | "
                "ForEach-Object { $_ -replace '.*:\\s+', '' }).Trim()"
            )
            ssid = out.strip()

        if not ssid:
            return {"error": "Not connected to any Wi-Fi network"}

        out = await self._run_powershell(f'netsh wlan show profile name="{ssid}" key=clear')
        password = ""
        for line in out.splitlines():
            if "Key Content" in line:
                password = line.split(":")[-1].strip()

        return {
            "ssid": ssid.strip(),
            "password": password or "No password (open network)",
        }

    async def get_ip_address(self) -> dict:
        out = await self._run_powershell(
            "Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -ne 'Loopback' } | "
            "Select-Object InterfaceAlias, IPAddress, PrefixLength | ConvertTo-Json"
        )
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        return {"interfaces": data}

    async def ping(self, host: str) -> dict:
        out = await self._run_powershell(
            f"Test-Connection -ComputerName {host} -Count 4 | Select-Object Address, "
            "ResponseTime, StatusCode | ConvertTo-Json"
        )
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        return {"host": host, "results": data}

    async def get_network_info(self) -> dict:
        adapters = await self._run_powershell(
            "Get-NetAdapter | Where-Object { $_.Status -eq 'Up' } | "
            "Select-Object Name, InterfaceDescription, LinkSpeed, Status | ConvertTo-Json"
        )
        ip = await self.get_ip_address()
        data = json.loads(adapters)
        if isinstance(data, dict):
            data = [data]
        return {"adapters": data, "ip": ip}

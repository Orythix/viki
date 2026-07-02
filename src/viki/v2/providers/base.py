"""Abstract system provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ShellResult:
    returncode: int
    stdout: str
    stderr: str


class SystemProvider(ABC):
    PLATFORM = "unknown"

    @abstractmethod
    async def get_os_info(self) -> dict:
        ...

    @abstractmethod
    async def get_hardware_info(self) -> dict:
        ...

    @abstractmethod
    async def get_cpu_info(self) -> dict:
        ...

    @abstractmethod
    async def get_ram_info(self) -> dict:
        ...

    @abstractmethod
    async def get_disk_info(self) -> list[dict]:
        ...

    @abstractmethod
    async def get_running_processes(self) -> list[dict]:
        ...

    @abstractmethod
    async def get_installed_software(self) -> list[dict]:
        ...

    @abstractmethod
    async def get_wifi_password(self, ssid: str | None = None) -> dict:
        ...

    @abstractmethod
    async def get_ip_address(self) -> dict:
        ...

    @abstractmethod
    async def ping(self, host: str) -> dict:
        ...

    @abstractmethod
    async def get_network_info(self) -> dict:
        ...

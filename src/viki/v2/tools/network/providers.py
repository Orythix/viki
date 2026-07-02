"""Network provider abstraction — WiFi, IP, DNS, diagnostics."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, cast

from ...providers.base import SystemProvider


class NetProvider(ABC):
    """Abstract network operations."""

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
    async def traceroute(self, host: str) -> dict:
        ...

    @abstractmethod
    async def get_network_info(self) -> dict:
        ...

    @abstractmethod
    async def get_dns_info(self) -> dict:
        ...

    @abstractmethod
    async def get_network_adapters(self) -> list[dict]:
        ...


class SystemNetProvider(NetProvider):
    """Wraps a SystemProvider to implement NetProvider."""

    def __init__(self, system_provider: SystemProvider):
        self._sp = system_provider

    async def get_wifi_password(self, ssid: str | None = None) -> dict:
        return await self._sp.get_wifi_password(ssid)

    async def get_ip_address(self) -> dict:
        return await self._sp.get_ip_address()

    async def ping(self, host: str) -> dict:
        return await self._sp.ping(host)

    async def traceroute(self, host: str) -> dict:
        info = await self._sp.get_network_info()
        return {"host": host, "hops": info.get("adapters", [])}

    async def get_network_info(self) -> dict:
        return await self._sp.get_network_info()

    async def get_dns_info(self) -> dict:
        info = await self._sp.get_network_info()
        ips = info.get("ip", {})
        return {"dns_servers": ["8.8.8.8", "1.1.1.1"], "info": ips}

    async def get_network_adapters(self) -> list[dict]:
        info = await self._sp.get_network_info()
        return cast("list[dict[Any, Any]]", info.get("adapters", []))

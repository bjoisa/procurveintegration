"""Async REST API client for ArubaOS-Switch (HP/Aruba ProCurve)."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import aiohttp

from .const import API_VERSIONS_PROBE_ORDER, LOGIN_SESSIONS_PATH

_LOGGER = logging.getLogger(__name__)


class CannotConnect(Exception):
    """Raised when the switch is unreachable."""


class InvalidAuth(Exception):
    """Raised when credentials are rejected."""


class ApiError(Exception):
    """Raised on unexpected API errors."""


@dataclass
class PortInfo:
    id: str
    name: str
    is_port_up: bool
    is_port_enabled: bool
    speed_mbps: int | None = None
    is_poe_port: bool = False


@dataclass
class PortStats:
    id: str
    rx_bytes: int = 0
    tx_bytes: int = 0


@dataclass
class PoePortInfo:
    id: str
    is_poe_enabled: bool = False
    power_draw_watts: float = 0.0
    poe_status: str = "Unknown"


@dataclass
class SystemInfo:
    hostname: str = ""
    firmware_version: str = ""
    serial_number: str = ""
    mac_address: str = ""
    uptime_seconds: int = 0
    cpu_percent: int = 0
    memory_percent: int = 0
    total_poe_watts: float = 0.0
    poe_budget_watts: float = 0.0


@dataclass
class SystemStatus:
    temperatures: list[dict[str, Any]] = field(default_factory=list)
    fans: list[dict[str, Any]] = field(default_factory=list)
    power_supplies: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class MacEntry:
    mac_address: str
    port_id: str
    vlan_id: int


@dataclass
class ArpEntry:
    ip_address: str
    mac_address: str
    port_id: str | None = None


class ProCurveApiClient:
    """Async client for the ArubaOS-Switch REST API v7."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        verify_ssl: bool = False,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._verify_ssl = verify_ssl
        self._session = session
        self._owns_session = session is None
        self._cookie: str | None = None
        self._api_version: str | None = None
        self._base_url = f"https://{host}:{port}"

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            connector = aiohttp.TCPConnector(ssl=self._verify_ssl)
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session

    async def close(self) -> None:
        if self._owns_session and self._session:
            await self._session.close()
            self._session = None

    def _url(self, path: str) -> str:
        if self._api_version is None:
            raise ApiError("API version not yet detected; call authenticate() first")
        return f"{self._base_url}/rest/{self._api_version}{path}"

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self._cookie:
            headers["Cookie"] = self._cookie
        return headers

    async def authenticate(self) -> None:
        """Probe REST API versions in order and obtain a session cookie."""
        session = await self._get_session()
        payload = {"userName": self._username, "password": self._password}
        last_statuses: dict[str, int] = {}
        for version in API_VERSIONS_PROBE_ORDER:
            url = f"{self._base_url}/rest/{version}{LOGIN_SESSIONS_PATH}"
            try:
                async with session.post(
                    url,
                    json=payload,
                    headers={"Accept": "application/json"},
                    ssl=self._verify_ssl,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 401:
                        raise InvalidAuth("Invalid username or password")
                    if resp.status in (503, 404):
                        _LOGGER.debug(
                            "REST API %s not available (HTTP %s), trying next version",
                            version,
                            resp.status,
                        )
                        last_statuses[version] = resp.status
                        continue
                    if resp.status not in (200, 201):
                        last_statuses[version] = resp.status
                        continue
                    data = await resp.json()
                    self._cookie = data.get("cookie", "")
                    self._api_version = version
                    _LOGGER.debug("Using REST API version %s", version)
                    return
            except aiohttp.ClientConnectorError as err:
                raise CannotConnect(f"Cannot reach {self._host}:{self._port}") from err
            except asyncio.TimeoutError as err:
                raise CannotConnect(f"Timeout connecting to {self._host}") from err
        raise ApiError(
            f"No supported REST API version found on {self._host}. Tried: {last_statuses}"
        )

    async def _get(self, path: str) -> Any:
        """Perform an authenticated GET request, re-authenticating once on 401."""
        if not self._cookie:
            await self.authenticate()
        session = await self._get_session()
        for attempt in range(2):
            try:
                async with session.get(
                    self._url(path),
                    headers=self._headers(),
                    ssl=self._verify_ssl,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 401 and attempt == 0:
                        self._cookie = None
                        await self.authenticate()
                        continue
                    if resp.status != 200:
                        raise ApiError(f"GET {path} returned {resp.status}")
                    return await resp.json()
            except aiohttp.ClientConnectorError as err:
                raise CannotConnect(str(err)) from err
            except asyncio.TimeoutError as err:
                raise CannotConnect("Request timed out") from err
        raise ApiError(f"Failed to GET {path} after re-auth")

    async def _put(self, path: str, payload: dict[str, Any]) -> None:
        """Perform an authenticated PUT request."""
        if not self._cookie:
            await self.authenticate()
        session = await self._get_session()
        for attempt in range(2):
            try:
                async with session.put(
                    self._url(path),
                    json=payload,
                    headers=self._headers(),
                    ssl=self._verify_ssl,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 401 and attempt == 0:
                        self._cookie = None
                        await self.authenticate()
                        continue
                    if resp.status not in (200, 204):
                        raise ApiError(f"PUT {path} returned {resp.status}")
                    return
            except aiohttp.ClientConnectorError as err:
                raise CannotConnect(str(err)) from err
            except asyncio.TimeoutError as err:
                raise CannotConnect("Request timed out") from err
        raise ApiError(f"Failed to PUT {path} after re-auth")

    async def _post(self, path: str, payload: dict[str, Any] | None = None) -> None:
        """Perform an authenticated POST request."""
        if not self._cookie:
            await self.authenticate()
        session = await self._get_session()
        for attempt in range(2):
            try:
                async with session.post(
                    self._url(path),
                    json=payload or {},
                    headers=self._headers(),
                    ssl=self._verify_ssl,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 401 and attempt == 0:
                        self._cookie = None
                        await self.authenticate()
                        continue
                    if resp.status not in (200, 201, 204):
                        raise ApiError(f"POST {path} returned {resp.status}")
                    return
            except aiohttp.ClientConnectorError as err:
                raise CannotConnect(str(err)) from err
            except asyncio.TimeoutError as err:
                raise CannotConnect("Request timed out") from err
        raise ApiError(f"Failed to POST {path} after re-auth")

    async def get_system_info(self) -> SystemInfo:
        data = await self._get("/system")
        return SystemInfo(
            hostname=data.get("name", ""),
            firmware_version=data.get("firmware_version", ""),
            serial_number=data.get("serial_number", ""),
            mac_address=data.get("base_ethernet_address", {}).get("octets", ""),
            uptime_seconds=data.get("uptime", 0),
            cpu_percent=data.get("cpu_utilization_15_seconds_percent", 0),
            memory_percent=int(
                100
                - (
                    data.get("total_memory_in_bytes", 1) > 0
                    and data.get("free_memory_in_bytes", 0)
                    / data.get("total_memory_in_bytes", 1)
                    * 100
                    or 0
                )
            ),
        )

    async def get_system_status(self) -> SystemStatus:
        data = await self._get("/system/status")
        temps = [
            {
                "id": t.get("id", ""),
                "description": t.get("description", ""),
                "celsius": t.get("temperature_celsius", 0),
                "status": t.get("status", "Unknown"),
            }
            for t in data.get("temperature_sensor_element", [])
        ]
        fans = [
            {
                "id": f.get("id", ""),
                "description": f.get("description", ""),
                "status": f.get("status", "Unknown"),
            }
            for f in data.get("fan_element", [])
        ]
        psus = [
            {
                "id": p.get("id", ""),
                "description": p.get("description", ""),
                "status": p.get("status", "Unknown"),
            }
            for p in data.get("power_supply_element", [])
        ]
        return SystemStatus(temperatures=temps, fans=fans, power_supplies=psus)

    async def get_ports(self) -> list[PortInfo]:
        data = await self._get("/ports")
        return [
            PortInfo(
                id=p["id"],
                name=p.get("name", p["id"]),
                is_port_up=p.get("is_port_up", False),
                is_port_enabled=p.get("is_port_enabled", True),
                speed_mbps=_parse_speed(p.get("current_speed_mbps", 0)),
            )
            for p in data.get("port_element", [])
        ]

    async def get_port_statistics(self) -> list[PortStats]:
        data = await self._get("/port-statistics")
        return [
            PortStats(
                id=s["id"],
                rx_bytes=s.get("port_rx_bytes", 0),
                tx_bytes=s.get("port_tx_bytes", 0),
            )
            for s in data.get("port_statistics_element", [])
        ]

    async def get_poe_status(self) -> tuple[float, float]:
        """Return (total_watts_used, budget_watts)."""
        data = await self._get("/poe")
        used = data.get("secd_poe_power_used", 0)
        budget = data.get("secd_poe_power_available", 0)
        return float(used), float(budget)

    async def get_poe_ports(self) -> list[PoePortInfo]:
        data = await self._get("/poe/ports")
        return [
            PoePortInfo(
                id=p["port_id"],
                is_poe_enabled=p.get("is_poe_enabled", False),
                power_draw_watts=float(p.get("poe_power_draws_watts", 0.0)),
                poe_status=p.get("poe_detection_status", "Unknown"),
            )
            for p in data.get("port_poe_element", [])
        ]

    async def get_mac_table(self) -> list[MacEntry]:
        data = await self._get("/mac-table")
        return [
            MacEntry(
                mac_address=e.get("mac_address", ""),
                port_id=e.get("port_id", ""),
                vlan_id=e.get("vlan_id", 0),
            )
            for e in data.get("mac_table_entry_element", [])
        ]

    async def get_arp_table(self) -> list[ArpEntry]:
        data = await self._get("/arp-table")
        return [
            ArpEntry(
                ip_address=e.get("ip_address", {}).get("version", "") and _parse_ip(e.get("ip_address", {})),
                mac_address=e.get("mac_address", ""),
                port_id=e.get("port_id"),
            )
            for e in data.get("arp_entry_element", [])
        ]

    async def set_port_enabled(self, port_id: str, enabled: bool) -> None:
        await self._put(f"/ports/{port_id}", {"is_port_enabled": enabled})

    async def set_poe_enabled(self, port_id: str, enabled: bool) -> None:
        await self._put(f"/poe/ports/{port_id}", {"is_poe_enabled": enabled})

    async def reboot(self) -> None:
        await self._post("/system/reboot")


def _parse_speed(raw: Any) -> int | None:
    if isinstance(raw, int):
        return raw if raw > 0 else None
    return None


def _parse_ip(ip_obj: dict[str, Any]) -> str:
    """Convert an ArubaOS-Switch IP address object to a dotted-decimal string."""
    if "octets" in ip_obj:
        return ip_obj["octets"]
    return ""

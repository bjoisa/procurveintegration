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
    speed_mbps: int | None = None


@dataclass
class PoePortInfo:
    id: str
    is_poe_enabled: bool = False
    power_draw_watts: float = 0.0
    poe_status: str = "Unknown"


@dataclass
class SystemInfo:
    hostname: str = ""
    firmware_version: str | None = None
    serial_number: str | None = None
    mac_address: str | None = None
    uptime_seconds: int | None = None
    cpu_percent: int | None = None
    memory_percent: int | None = None
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
                    if resp.status == 404:
                        _LOGGER.debug(
                            "REST API %s not found (HTTP 404), trying next version",
                            version,
                        )
                        last_statuses[version] = resp.status
                        continue
                    if resp.status == 503:
                        _LOGGER.debug(
                            "REST API %s unavailable (HTTP 503), trying next version",
                            version,
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
        if last_statuses and all(s == 503 for s in last_statuses.values()):
            raise CannotConnect(
                f"REST API service unavailable on {self._host} (HTTP 503 — possibly a concurrent session limit)"
            )
        raise ApiError(
            f"No supported REST API version found on {self._host}. Tried: {last_statuses}"
        )

    async def _get(self, path: str, optional: bool = False) -> Any:
        """Perform an authenticated GET request, re-authenticating once on 401.

        If optional is True, returns None on 404 instead of raising ApiError.
        """
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
                    if resp.status == 404 and optional:
                        return None
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
        _LOGGER.debug("Raw /system response: %s", data)
        mod_data = await self._get("/management-module", optional=True)
        _LOGGER.debug("Raw /management-module response: %s", mod_data)
        mod = {}
        if isinstance(mod_data, dict):
            elements = mod_data.get("management_module_element", [])
            if elements:
                mod = elements[0]
        _fw = mod.get("firmware_version") or data.get("firmware_version") or None
        _ser = mod.get("serial_number") or data.get("serial_number") or None
        _mac = (
            mod.get("mac_address", {}).get("octets")
            or data.get("base_ethernet_address", {}).get("octets")
            or None
        )
        _uptime = mod["uptime"] if "uptime" in mod else data.get("uptime")
        _cpu = None
        if "cpu_utilization_15_seconds_percent" in mod:
            _cpu = mod["cpu_utilization_15_seconds_percent"]
        elif "cpu_utilization" in mod:
            _cpu = mod["cpu_utilization"]
        _total_mem = mod.get("total_memory_in_bytes", 0)
        _free_mem = mod.get("free_memory_in_bytes", 0)
        _mem = int(100 - (_free_mem / _total_mem * 100)) if _total_mem > 0 else None
        return SystemInfo(
            hostname=data.get("name", ""),
            firmware_version=_fw,
            serial_number=_ser,
            mac_address=_mac,
            uptime_seconds=_uptime,
            cpu_percent=_cpu,
            memory_percent=_mem,
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
        _LOGGER.debug(
            "Raw /ports sample: %s", data.get("port_element", [{}])[0]
        )
        return [
            PortInfo(
                id=p["id"],
                name=p.get("name") or p["id"],
                is_port_up=p.get("is_port_up", False),
                is_port_enabled=p.get("is_port_enabled", True),
            )
            for p in data.get("port_element", [])
        ]

    async def get_port_statistics(self) -> list[PortStats]:
        data = await self._get("/port-statistics")
        _LOGGER.debug(
            "Raw /port-statistics sample: %s",
            data.get("port_statistics_element", [{}])[0],
        )
        return [
            PortStats(
                id=s["id"],
                rx_bytes=s.get("bytes_rx", 0),
                tx_bytes=s.get("bytes_tx", 0),
                speed_mbps=_parse_speed(s.get("port_speed_mbps", 0)),
            )
            for s in data.get("port_statistics_element", [])
        ]

    async def get_poe_status(self) -> tuple[float, float]:
        """Return (total_watts_used, budget_watts), or (0.0, 0.0) if PoE REST endpoint is absent."""
        data = await self._get("/poe", optional=True)
        if data is None:
            return (0.0, 0.0)
        used = data.get("secd_poe_power_used", 0)
        budget = data.get("secd_poe_power_available", 0)
        return float(used), float(budget)

    async def get_poe_ports(self) -> list[PoePortInfo]:
        """Return PoE port list, or [] if PoE REST endpoint is absent."""
        data = await self._get("/poe/ports", optional=True)
        if data is None:
            return []
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
        current = await self._get(f"/ports/{port_id}")
        current.pop("uri", None)
        current["is_port_enabled"] = enabled
        await self._put(f"/ports/{port_id}", current)

    async def set_poe_enabled(self, port_id: str, enabled: bool) -> None:
        current = await self._get(f"/poe/ports/{port_id}")
        current.pop("uri", None)
        current["is_poe_enabled"] = enabled
        await self._put(f"/poe/ports/{port_id}", current)

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

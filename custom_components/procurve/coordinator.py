"""DataUpdateCoordinator for HP/Aruba ProCurve."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    ArpEntry,
    MacEntry,
    PoePortInfo,
    PortInfo,
    PortStats,
    ProCurveApiClient,
    SystemInfo,
    SystemStatus,
    CannotConnect,
    ApiError,
)
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class ProCurveData:
    system_info: SystemInfo
    system_status: SystemStatus
    ports: list[PortInfo] = field(default_factory=list)
    port_stats: dict[str, PortStats] = field(default_factory=dict)
    poe_ports: dict[str, PoePortInfo] = field(default_factory=dict)
    total_poe_watts: float = 0.0
    poe_budget_watts: float = 0.0
    mac_table: list[MacEntry] = field(default_factory=list)
    arp_table: list[ArpEntry] = field(default_factory=list)


class ProCurveCoordinator(DataUpdateCoordinator[ProCurveData]):
    """Fetches all data from the switch in a single poll cycle."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: ProCurveApiClient,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client

    async def _async_update_data(self) -> ProCurveData:
        try:
            (
                system_info,
                system_status,
                ports,
                port_stats_list,
                poe_ports_list,
                poe_totals,
                mac_table,
                arp_table,
            ) = await _gather_all(self.client)
        except CannotConnect as err:
            raise UpdateFailed(f"Cannot connect to switch: {err}") from err
        except ApiError as err:
            raise UpdateFailed(f"API error: {err}") from err

        total_poe, poe_budget = poe_totals
        port_stats = {s.id: s for s in port_stats_list}
        poe_ports = {p.id: p for p in poe_ports_list}

        poe_port_ids = {p.id for p in poe_ports_list}
        for port in ports:
            port.is_poe_port = port.id in poe_port_ids
            if port.id in port_stats:
                port.speed_mbps = port_stats[port.id].speed_mbps

        return ProCurveData(
            system_info=system_info,
            system_status=system_status,
            ports=ports,
            port_stats=port_stats,
            poe_ports=poe_ports,
            total_poe_watts=total_poe,
            poe_budget_watts=poe_budget,
            mac_table=mac_table,
            arp_table=arp_table,
        )


async def _gather_all(client: ProCurveApiClient):
    """Run all API calls. Sequential to avoid hammering the switch."""
    system_info = await client.get_system_info()
    system_status = await client.get_system_status()
    ports = await client.get_ports()
    port_stats = await client.get_port_statistics()
    poe_ports = await client.get_poe_ports()
    poe_totals = await client.get_poe_status()
    mac_table = await client.get_mac_table()
    arp_table = await client.get_arp_table()
    return (
        system_info,
        system_status,
        ports,
        port_stats,
        poe_ports,
        poe_totals,
        mac_table,
        arp_table,
    )

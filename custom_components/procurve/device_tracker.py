"""Device tracker platform for HP/Aruba ProCurve (connected hosts)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.device_tracker import ScannerEntity, SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ProCurveCoordinator
from .entity import ProCurveEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ProCurveCoordinator = hass.data[DOMAIN][entry.entry_id]

    tracked: set[str] = set()

    @callback
    def _async_update_from_coordinator() -> None:
        new_entities = []
        ip_by_mac = {e.mac_address: e.ip_address for e in coordinator.data.arp_table}
        port_by_mac = {e.mac_address: e.port_id for e in coordinator.data.mac_table}

        for entry_mac in coordinator.data.mac_table:
            mac = entry_mac.mac_address
            if mac in tracked:
                continue
            tracked.add(mac)
            new_entities.append(
                ProCurveConnectedDevice(
                    coordinator,
                    mac,
                    ip_by_mac.get(mac),
                    port_by_mac.get(mac),
                )
            )

        if new_entities:
            async_add_entities(new_entities)

    coordinator.async_add_listener(_async_update_from_coordinator)
    _async_update_from_coordinator()


class ProCurveConnectedDevice(ProCurveEntity, ScannerEntity):
    _attr_source_type = SourceType.ROUTER

    def __init__(
        self,
        coordinator: ProCurveCoordinator,
        mac: str,
        ip_address: str | None,
        port_id: str | None,
    ) -> None:
        super().__init__(coordinator)
        self._mac = mac
        self._ip = ip_address
        self._port_id = port_id
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_host_{mac.replace(':', '')}"
        self._attr_name = mac

    @property
    def is_connected(self) -> bool:
        current_macs = {e.mac_address for e in self.coordinator.data.mac_table}
        return self._mac in current_macs

    @property
    def ip_address(self) -> str | None:
        for entry in self.coordinator.data.arp_table:
            if entry.mac_address == self._mac:
                return entry.ip_address
        return self._ip

    @property
    def mac_address(self) -> str:
        return self._mac

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        port_id = next(
            (e.port_id for e in self.coordinator.data.mac_table if e.mac_address == self._mac),
            self._port_id,
        )
        return {"port": port_id}

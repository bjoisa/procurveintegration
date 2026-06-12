"""Switch platform for HP/Aruba ProCurve (PoE and port admin control)."""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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

    entities: list[SwitchEntity] = []

    for port in coordinator.data.ports:
        entities.append(ProCurvePortAdminSwitch(coordinator, port.id, port.name))
        if port.is_poe_port:
            entities.append(ProCurvePoeSwitch(coordinator, port.id, port.name))

    async_add_entities(entities)


class ProCurvePortAdminSwitch(ProCurveEntity, SwitchEntity):
    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(self, coordinator: ProCurveCoordinator, port_id: str, port_name: str) -> None:
        super().__init__(coordinator)
        self._port_id = port_id
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_port_{port_id}_admin"
        self._attr_name = f"Port {port_name} Enabled"

    @property
    def is_on(self) -> bool:
        for port in self.coordinator.data.ports:
            if port.id == self._port_id:
                return port.is_port_enabled
        return False

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.client.set_port_enabled(self._port_id, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.client.set_port_enabled(self._port_id, False)
        await self.coordinator.async_request_refresh()


class ProCurvePoeSwitch(ProCurveEntity, SwitchEntity):
    _attr_device_class = SwitchDeviceClass.OUTLET

    def __init__(self, coordinator: ProCurveCoordinator, port_id: str, port_name: str) -> None:
        super().__init__(coordinator)
        self._port_id = port_id
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_port_{port_id}_poe"
        self._attr_name = f"Port {port_name} PoE"

    @property
    def is_on(self) -> bool:
        poe = self.coordinator.data.poe_ports.get(self._port_id)
        if poe is None:
            return False
        return poe.is_poe_enabled

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.client.set_poe_enabled(self._port_id, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.client.set_poe_enabled(self._port_id, False)
        await self.coordinator.async_request_refresh()

"""Binary sensor platform for HP/Aruba ProCurve."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ProCurveCoordinator
from .entity import ProCurveEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ProCurveCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[BinarySensorEntity] = []

    for port in coordinator.data.ports:
        entities.append(ProCurvePortLinkSensor(coordinator, port.id, port.name))

    for fan in coordinator.data.system_status.fans:
        entities.append(ProCurveFanSensor(coordinator, fan["id"], fan.get("description", fan["id"])))

    for psu in coordinator.data.system_status.power_supplies:
        entities.append(ProCurvePsuSensor(coordinator, psu["id"], psu.get("description", psu["id"])))

    async_add_entities(entities)


class ProCurvePortLinkSensor(ProCurveEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: ProCurveCoordinator, port_id: str, port_name: str) -> None:
        super().__init__(coordinator)
        self._port_id = port_id
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_port_{port_id}_link"
        self._attr_name = f"Port {port_name} Link"

    @property
    def is_on(self) -> bool:
        for port in self.coordinator.data.ports:
            if port.id == self._port_id:
                return port.is_port_up
        return False


class ProCurveFanSensor(ProCurveEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: ProCurveCoordinator, fan_id: str, description: str) -> None:
        super().__init__(coordinator)
        self._fan_id = fan_id
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_fan_{fan_id}"
        self._attr_name = f"Fan {description}"

    @property
    def is_on(self) -> bool:
        for fan in self.coordinator.data.system_status.fans:
            if fan["id"] == self._fan_id:
                return fan.get("status", "").lower() not in ("ok", "good", "normal")
        return False


class ProCurvePsuSensor(ProCurveEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: ProCurveCoordinator, psu_id: str, description: str) -> None:
        super().__init__(coordinator)
        self._psu_id = psu_id
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_psu_{psu_id}"
        self._attr_name = f"PSU {description}"

    @property
    def is_on(self) -> bool:
        for psu in self.coordinator.data.system_status.power_supplies:
            if psu["id"] == self._psu_id:
                return psu.get("status", "").lower() not in ("ok", "good", "normal")
        return False

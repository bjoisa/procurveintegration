"""Sensor platform for HP/Aruba ProCurve."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfDataRate,
    UnitOfEnergy,
    UnitOfInformation,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import ProCurveCoordinator, ProCurveData
from .const import DOMAIN
from .entity import ProCurveEntity


@dataclass(frozen=True, kw_only=True)
class ProCurveSensorDescription(SensorEntityDescription):
    value_fn: Callable[[ProCurveData], float | int | str | None]


SYSTEM_SENSORS: tuple[ProCurveSensorDescription, ...] = (
    ProCurveSensorDescription(
        key="cpu_percent",
        translation_key="cpu_percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.system_info.cpu_percent,
    ),
    ProCurveSensorDescription(
        key="memory_percent",
        translation_key="memory_percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.system_info.memory_percent,
    ),
    ProCurveSensorDescription(
        key="uptime",
        translation_key="uptime",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.system_info.uptime_seconds,
    ),
    ProCurveSensorDescription(
        key="total_poe_watts",
        translation_key="total_poe_watts",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: round(d.total_poe_watts, 1),
    ),
    ProCurveSensorDescription(
        key="firmware_version",
        translation_key="firmware_version",
        value_fn=lambda d: d.system_info.firmware_version,
    ),
    ProCurveSensorDescription(
        key="temperature",
        translation_key="temperature",
        native_unit_of_measurement="°C",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _first_temperature(d),
    ),
)


def _first_temperature(data: ProCurveData) -> float | None:
    temps = data.system_status.temperatures
    if temps:
        return temps[0].get("celsius")
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ProCurveCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = []

    for desc in SYSTEM_SENSORS:
        entities.append(ProCurveSystemSensor(coordinator, desc))

    for port in coordinator.data.ports:
        entities.append(ProCurvePortRxSensor(coordinator, port.id, port.name))
        entities.append(ProCurvePortTxSensor(coordinator, port.id, port.name))
        entities.append(ProCurvePortSpeedSensor(coordinator, port.id, port.name))
        if port.is_poe_port:
            entities.append(ProCurvePoePowerSensor(coordinator, port.id, port.name))

    async_add_entities(entities)


class ProCurveSystemSensor(ProCurveEntity, SensorEntity):
    entity_description: ProCurveSensorDescription

    def __init__(
        self,
        coordinator: ProCurveCoordinator,
        description: ProCurveSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"

    @property
    def native_value(self):
        return self.entity_description.value_fn(self.coordinator.data)


class ProCurvePortRxSensor(ProCurveEntity, SensorEntity):
    _attr_native_unit_of_measurement = UnitOfInformation.MEGABYTES
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, coordinator: ProCurveCoordinator, port_id: str, port_name: str) -> None:
        super().__init__(coordinator)
        self._port_id = port_id
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_port_{port_id}_rx"
        self._attr_translation_key = "port_rx"
        self._attr_translation_placeholders = {"port": port_name}
        self._attr_name = f"Port {port_name} RX"

    @property
    def native_value(self) -> float | None:
        stats = self.coordinator.data.port_stats.get(self._port_id)
        if stats is None:
            return None
        return round(stats.rx_bytes / 1_048_576, 2)


class ProCurvePortTxSensor(ProCurveEntity, SensorEntity):
    _attr_native_unit_of_measurement = UnitOfInformation.MEGABYTES
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, coordinator: ProCurveCoordinator, port_id: str, port_name: str) -> None:
        super().__init__(coordinator)
        self._port_id = port_id
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_port_{port_id}_tx"
        self._attr_name = f"Port {port_name} TX"

    @property
    def native_value(self) -> float | None:
        stats = self.coordinator.data.port_stats.get(self._port_id)
        if stats is None:
            return None
        return round(stats.tx_bytes / 1_048_576, 2)


class ProCurvePortSpeedSensor(ProCurveEntity, SensorEntity):
    _attr_native_unit_of_measurement = "Mbit/s"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: ProCurveCoordinator, port_id: str, port_name: str) -> None:
        super().__init__(coordinator)
        self._port_id = port_id
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_port_{port_id}_speed"
        self._attr_name = f"Port {port_name} Speed"

    @property
    def native_value(self) -> int | None:
        for port in self.coordinator.data.ports:
            if port.id == self._port_id:
                return port.speed_mbps
        return None


class ProCurvePoePowerSensor(ProCurveEntity, SensorEntity):
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: ProCurveCoordinator, port_id: str, port_name: str) -> None:
        super().__init__(coordinator)
        self._port_id = port_id
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_port_{port_id}_poe_power"
        self._attr_name = f"Port {port_name} PoE Power"

    @property
    def native_value(self) -> float | None:
        poe = self.coordinator.data.poe_ports.get(self._port_id)
        if poe is None:
            return None
        return round(poe.power_draw_watts, 1)

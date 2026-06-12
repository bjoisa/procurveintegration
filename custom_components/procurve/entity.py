"""Base entity for HP/Aruba ProCurve."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ProCurveCoordinator


class ProCurveEntity(CoordinatorEntity[ProCurveCoordinator]):
    """Base class for all ProCurve entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ProCurveCoordinator) -> None:
        super().__init__(coordinator)
        info = coordinator.data.system_info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            name=info.hostname or coordinator.config_entry.data.get("host", "ProCurve"),
            manufacturer="HP/Aruba",
            model="ProCurve (ArubaOS-Switch)",
            sw_version=info.firmware_version,
            serial_number=info.serial_number,
        )

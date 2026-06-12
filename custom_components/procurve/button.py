"""Button platform for HP/Aruba ProCurve (reboot)."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
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
    async_add_entities([ProCurveRebootButton(coordinator)])


class ProCurveRebootButton(ProCurveEntity, ButtonEntity):
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_translation_key = "restart"

    def __init__(self, coordinator: ProCurveCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_reboot"
        self._attr_name = "Restart"

    async def async_press(self) -> None:
        _LOGGER.warning(
            "Rebooting ProCurve switch %s",
            coordinator_host(self.coordinator),
        )
        await self.coordinator.client.reboot()


def coordinator_host(coordinator: ProCurveCoordinator) -> str:
    return coordinator.config_entry.data.get("host", "unknown")

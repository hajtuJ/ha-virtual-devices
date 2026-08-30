"""Problem binary sensor platform for Virtual Gate."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .gate import GateProblem

if TYPE_CHECKING:
    from collections.abc import Mapping

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import VirtualDevicesConfigEntry
    from .gate import GateController


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VirtualDevicesConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the gate problem diagnostic."""
    del hass
    async_add_entities([VirtualGateProblemEntity(entry)])


class VirtualGateProblemEntity(BinarySensorEntity):
    """Expose whether the controller has an active problem."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "problem"

    def __init__(self, entry: VirtualDevicesConfigEntry) -> None:
        """Bind the problem entity to the entry-owned controller."""
        config = entry.runtime_data.config
        self._controller: GateController = entry.runtime_data.controller
        self._attr_unique_id = f"{config.device_id}_problem"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config.device_id)},
            name=config.name,
            manufacturer="Virtual Devices",
            model="Virtual Gate",
        )

    @property
    def is_on(self) -> bool:
        """Return whether a semantic problem is active."""
        return self._controller.snapshot.problem is not GateProblem.NONE

    @property
    def extra_state_attributes(self) -> Mapping[str, str]:
        """Expose the specific translated diagnostic code."""
        return {"problem": self._controller.snapshot.problem.value}

    async def async_added_to_hass(self) -> None:
        """Subscribe state writes to controller updates."""
        self.async_on_remove(
            self._controller.async_add_update_callback(self.async_write_ha_state)
        )

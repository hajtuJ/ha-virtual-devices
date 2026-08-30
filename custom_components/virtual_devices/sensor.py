"""Diagnostic sensor platform for Virtual Gate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .gate import GateCommand, GateDirection, GateSnapshot, GateState

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import VirtualDevicesConfigEntry
    from .gate import GateController

type SensorValue = str | None


@dataclass(frozen=True, slots=True)
class GateSensorDescription:
    """Describe one cached semantic diagnostic."""

    key: str
    options: tuple[str, ...]
    value_fn: Callable[[GateSnapshot], SensorValue]
    enabled_default: bool


SENSORS = (
    GateSensorDescription(
        key="detailed_state",
        options=tuple(state.value for state in GateState),
        value_fn=lambda snapshot: snapshot.state.value,
        enabled_default=True,
    ),
    GateSensorDescription(
        key="last_direction",
        options=tuple(direction.value for direction in GateDirection),
        value_fn=lambda snapshot: snapshot.last_direction.value,
        enabled_default=False,
    ),
    GateSensorDescription(
        key="last_command",
        options=tuple(command.value for command in GateCommand),
        value_fn=lambda snapshot: (
            snapshot.last_command.value if snapshot.last_command is not None else None
        ),
        enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VirtualDevicesConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up semantic diagnostic sensors for one gate."""
    del hass
    async_add_entities(
        [VirtualGateSensorEntity(entry, description) for description in SENSORS]
    )


class VirtualGateSensorEntity(SensorEntity):
    """Expose one cached domain field as an enum diagnostic sensor."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        entry: VirtualDevicesConfigEntry,
        description: GateSensorDescription,
    ) -> None:
        """Bind one immutable description to one controller."""
        config = entry.runtime_data.config
        self._controller: GateController = entry.runtime_data.controller
        self._description = description
        self._attr_unique_id = f"{config.device_id}_{description.key}"
        self._attr_translation_key = description.key
        self._attr_options = list(description.options)
        self._attr_entity_registry_enabled_default = description.enabled_default
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config.device_id)},
            name=config.name,
            manufacturer="Virtual Devices",
            model="Virtual Gate",
        )

    @property
    def native_value(self) -> SensorValue:
        """Return a cached semantic value."""
        return self._description.value_fn(self._controller.snapshot)

    async def async_added_to_hass(self) -> None:
        """Subscribe state writes to controller updates."""
        self.async_on_remove(
            self._controller.async_add_update_callback(self.async_write_ha_state)
        )

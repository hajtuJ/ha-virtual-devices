"""Cover platform for Virtual Gate."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .gate import GateController, GateState

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import VirtualDevicesConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VirtualDevicesConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the single cover owned by this gate config entry."""
    del hass
    async_add_entities([VirtualGateCoverEntity(entry)])


class VirtualGateCoverEntity(CoverEntity):
    """Thin Home Assistant representation of a Virtual Gate controller."""

    _attr_device_class = CoverDeviceClass.GATE
    _attr_has_entity_name = True
    _attr_name = None
    _attr_should_poll = False

    def __init__(self, entry: VirtualDevicesConfigEntry) -> None:
        """Bind cached entity properties to one entry-owned controller."""
        self._entry = entry
        self._controller: GateController = entry.runtime_data.controller
        config = entry.runtime_data.config
        self._attr_unique_id = f"{config.device_id}_gate"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config.device_id)},
            name=config.name,
            manufacturer="Virtual Devices",
            model="Virtual Gate",
        )
        features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE
        if self._controller.supports_stop:
            features |= CoverEntityFeature.STOP
        self._attr_supported_features = features

    @property
    def available(self) -> bool:
        """Return cached control availability without hiding logical state."""
        return self._controller.control_available

    @property
    def is_closed(self) -> bool | None:
        """Map only authoritative CLOSED state to true."""
        state = self._controller.snapshot.state
        if state is GateState.CLOSED:
            return True
        if state in (
            GateState.OPEN,
            GateState.OPENING,
            GateState.CLOSING,
            GateState.STOPPED,
        ):
            return False
        return None

    @property
    def is_opening(self) -> bool:
        """Return cached opening state."""
        return self._controller.snapshot.state is GateState.OPENING

    @property
    def is_closing(self) -> bool:
        """Return cached closing state."""
        return self._controller.snapshot.state is GateState.CLOSING

    @property
    def current_cover_position(self) -> int | None:
        """Return the clamped cached estimate without enabling SET_POSITION."""
        position = self._controller.snapshot.estimated_position
        return round(position) if position is not None else None

    async def async_added_to_hass(self) -> None:
        """Subscribe entity writes to controller updates."""
        self.async_on_remove(
            self._controller.async_add_update_callback(
                self.async_write_ha_state,
            )
        )

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Delegate OPEN to the safety controller."""
        del kwargs
        await self._controller.async_open()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Delegate CLOSE to the safety controller."""
        del kwargs
        await self._controller.async_close()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Delegate configured STOP to the safety controller."""
        del kwargs
        await self._controller.async_stop()

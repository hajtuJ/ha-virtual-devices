"""Home Assistant service adapter for Virtual Gate command sources."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.button.const import SERVICE_PRESS
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .command_models import SourceRef


class HomeAssistantSourceActions:
    """Call the switch and button services supported by the MVP."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Bind source operations to one Home Assistant instance."""
        self._hass = hass

    async def async_is_available(self, source: SourceRef) -> bool:
        """Return whether Home Assistant currently has a usable source state."""
        state = self._hass.states.get(source.entity_id)
        return state is not None and state.state not in (
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
        )

    async def async_activate(self, source: SourceRef) -> None:
        """Turn on a configured switch source and await service completion."""
        await self._call(source, SERVICE_TURN_ON)

    async def async_deactivate(self, source: SourceRef) -> None:
        """Turn off a configured switch source and await service completion."""
        await self._call(source, SERVICE_TURN_OFF)

    async def async_press(self, source: SourceRef) -> None:
        """Press a configured button source and await service completion."""
        await self._call(source, SERVICE_PRESS)

    async def _call(self, source: SourceRef, service: str) -> None:
        """Call the entity's validated domain service."""
        await self._hass.services.async_call(
            source.action_type.value,
            service,
            {ATTR_ENTITY_ID: source.entity_id},
            blocking=True,
        )

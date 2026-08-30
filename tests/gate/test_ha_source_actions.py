"""Tests for the Home Assistant source service adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from custom_components.virtual_devices.gate import ControlActionType, SourceRef
from custom_components.virtual_devices.gate.ha_source_actions import (
    HomeAssistantSourceActions,
)
from homeassistant.const import STATE_UNAVAILABLE

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, ServiceCall


async def test_source_adapter_calls_supported_mvp_services(
    hass: HomeAssistant,
) -> None:
    """Switch and button operations use blocking entity service calls."""
    calls: list[tuple[str, str]] = []

    async def record_switch(call: ServiceCall) -> None:
        calls.append(("switch", call.service))

    async def record_button(call: ServiceCall) -> None:
        calls.append(("button", call.service))

    hass.services.async_register("switch", "turn_on", record_switch)
    hass.services.async_register("switch", "turn_off", record_switch)
    hass.services.async_register("button", "press", record_button)
    hass.states.async_set("switch.gate", "off")
    hass.states.async_set("button.gate", "unknown_but_valid")

    adapter = HomeAssistantSourceActions(hass)
    switch = SourceRef("switch.gate", ControlActionType.SWITCH)
    button = SourceRef("button.gate", ControlActionType.BUTTON)
    assert await adapter.async_is_available(switch)
    assert await adapter.async_is_available(button)

    await adapter.async_activate(switch)
    await adapter.async_deactivate(switch)
    await adapter.async_press(button)
    assert calls == [
        ("switch", "turn_on"),
        ("switch", "turn_off"),
        ("button", "press"),
    ]


async def test_source_adapter_rejects_missing_unknown_and_unavailable_states(
    hass: HomeAssistant,
) -> None:
    """Availability preflight follows Home Assistant state semantics."""
    adapter = HomeAssistantSourceActions(hass)
    missing = SourceRef("switch.missing", ControlActionType.SWITCH)
    unavailable = SourceRef("switch.unavailable", ControlActionType.SWITCH)
    hass.states.async_set(unavailable.entity_id, STATE_UNAVAILABLE)

    assert not await adapter.async_is_available(missing)
    assert not await adapter.async_is_available(unavailable)

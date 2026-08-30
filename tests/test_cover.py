"""Home Assistant platform tests for Virtual Gate covers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from custom_components.virtual_devices.const import DOMAIN
from custom_components.virtual_devices.gate import (
    ControlActionType,
    ControlMode,
    GateConfig,
    SourceRef,
    StopStrategyType,
)
from homeassistant.components.cover import CoverEntityFeature
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_SUPPORTED_FEATURES,
    STATE_OPENING,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (  # type: ignore[import-untyped]
    MockConfigEntry,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, ServiceCall


def gate_config(device_id: str, button: str, name: str = "Gate") -> GateConfig:
    """Build a valid gate backed by a momentary button."""
    return GateConfig(
        device_id=device_id,
        name=name,
        control_mode=ControlMode.SINGLE_STEP,
        step_source=SourceRef(button, ControlActionType.BUTTON),
        minimum_command_interval_ms=0,
    )


async def setup_gate(hass: HomeAssistant, config: GateConfig) -> MockConfigEntry:
    """Add and set up one entry with all source states available."""
    for source in config.control_sources:
        hass.states.async_set(source.entity_id, "off")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=config.name,
        unique_id=config.device_id,
        data=config.to_dict(),
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_cover_properties_delegation_and_no_set_position(
    hass: HomeAssistant,
) -> None:
    calls: list[ServiceCall] = []

    async def record(call: ServiceCall) -> None:
        calls.append(call)

    hass.services.async_register("button", "press", record)
    entry = await setup_gate(
        hass, gate_config("driveway-id", "button.driveway", "Driveway Gate")
    )
    entity_id = "cover.driveway_gate"
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == STATE_UNKNOWN
    assert state.attributes[ATTR_DEVICE_CLASS] == "gate"
    assert state.attributes[ATTR_SUPPORTED_FEATURES] == int(
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE
    )
    assert not state.attributes[ATTR_SUPPORTED_FEATURES] & int(
        CoverEntityFeature.SET_POSITION | CoverEntityFeature.STOP
    )

    await hass.services.async_call(
        "cover", "open_cover", {"entity_id": entity_id}, blocking=True
    )
    assert [call.domain + "." + call.service for call in calls] == ["button.press"]
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == STATE_OPENING

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    unloaded_state = hass.states.get(entity_id)
    assert unloaded_state is not None
    assert unloaded_state.state == STATE_UNAVAILABLE
    assert len(calls) == 1


async def test_stop_feature_is_dynamic_and_two_devices_are_distinct(
    hass: HomeAssistant,
) -> None:
    calls: list[str] = []

    async def record(call: ServiceCall) -> None:
        calls.append(str(call.data["entity_id"]))

    hass.services.async_register("button", "press", record)
    first = gate_config("first-id", "button.first", "First Gate")
    second = GateConfig(
        device_id="second-id",
        name="Second Gate",
        control_mode=ControlMode.SEPARATE_OPEN_CLOSE_STOP,
        open_source=SourceRef("button.second_open", ControlActionType.BUTTON),
        close_source=SourceRef("button.second_close", ControlActionType.BUTTON),
        stop_source=SourceRef("button.second_stop", ControlActionType.BUTTON),
        stop_strategy=StopStrategyType.DEDICATED,
        minimum_command_interval_ms=0,
    )
    first_entry = await setup_gate(hass, first)
    second_entry = await setup_gate(hass, second)

    first_state = hass.states.get("cover.first_gate")
    second_state = hass.states.get("cover.second_gate")
    assert first_state is not None
    assert second_state is not None
    assert not first_state.attributes[ATTR_SUPPORTED_FEATURES] & int(
        CoverEntityFeature.STOP
    )
    assert second_state.attributes[ATTR_SUPPORTED_FEATURES] & int(
        CoverEntityFeature.STOP
    )

    device_registry = dr.async_get(hass)
    first_device = device_registry.async_get_device(identifiers={(DOMAIN, "first-id")})
    second_device = device_registry.async_get_device(
        identifiers={(DOMAIN, "second-id")}
    )
    assert first_device is not None
    assert second_device is not None
    assert first_device.id != second_device.id
    assert first_device.config_entries == {first_entry.entry_id}
    assert second_device.config_entries == {second_entry.entry_id}

    entity_registry = er.async_get(hass)
    first_entity = entity_registry.async_get("cover.first_gate")
    second_entity = entity_registry.async_get("cover.second_gate")
    assert first_entity is not None
    assert first_entity.device_id == first_device.id
    assert second_entity is not None
    assert second_entity.device_id == second_device.id
    assert first_entity.unique_id == "first-id_gate"
    assert second_entity.unique_id == "second-id_gate"

    await hass.services.async_call(
        "cover", "open_cover", {"entity_id": "cover.first_gate"}, blocking=True
    )
    await hass.services.async_call(
        "cover", "open_cover", {"entity_id": "cover.second_gate"}, blocking=True
    )
    first_opening = hass.states.get("cover.first_gate")
    second_opening = hass.states.get("cover.second_gate")
    assert first_opening is not None
    assert second_opening is not None
    assert first_opening.state == STATE_OPENING
    assert second_opening.state == STATE_OPENING
    assert calls == ["button.first", "button.second_open"]

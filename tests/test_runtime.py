"""HA runtime tests for observation, restore, timers, and diagnostics entities."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import TYPE_CHECKING

import pytest
from custom_components.virtual_devices.const import DOMAIN
from custom_components.virtual_devices.gate import (
    ControlActionType,
    ControlMode,
    GateConfig,
    GateLimitConfig,
    GateProblem,
    GateState,
    SourceRef,
)
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (  # type: ignore[import-untyped]
    MockConfigEntry,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, ServiceCall


def observed_config(*, debounce_ms: int = 0) -> GateConfig:
    """Build a fully observed gate with fast button control."""
    return GateConfig(
        device_id="observed-id",
        name="Observed Gate",
        control_mode=ControlMode.SINGLE_STEP,
        step_source=SourceRef("button.observed_gate", ControlActionType.BUTTON),
        open_limit=GateLimitConfig("binary_sensor.gate_open", debounce_ms=debounce_ms),
        closed_limit=GateLimitConfig(
            "binary_sensor.gate_closed", debounce_ms=debounce_ms
        ),
        obstacle_source="binary_sensor.gate_obstacle",
        minimum_command_interval_ms=0,
    )


async def setup_observed_gate(
    hass: HomeAssistant,
    config: GateConfig,
) -> MockConfigEntry:
    """Set up one entry after its physical sources have states."""
    hass.states.async_set("button.observed_gate", STATE_OFF)
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


async def test_limits_external_motion_conflict_and_diagnostic_entities(
    hass: HomeAssistant,
) -> None:
    calls: list[ServiceCall] = []

    async def record(call: ServiceCall) -> None:
        calls.append(call)

    hass.services.async_register("button", "press", record)
    hass.states.async_set("binary_sensor.gate_open", STATE_OFF)
    hass.states.async_set("binary_sensor.gate_closed", STATE_ON)
    hass.states.async_set("binary_sensor.gate_obstacle", STATE_OFF)
    entry = await setup_observed_gate(hass, observed_config())
    controller = entry.runtime_data.controller

    assert controller.snapshot.state.value == GateState.CLOSED.value
    assert controller.snapshot.estimated_position == 0
    assert controller.sensor_available
    detailed = hass.states.get("sensor.observed_gate_detailed_state")
    problem = hass.states.get("binary_sensor.observed_gate_problem")
    assert detailed is not None
    assert detailed.state == GateState.CLOSED.value
    assert problem is not None
    assert problem.state == STATE_OFF

    hass.states.async_set("binary_sensor.gate_closed", STATE_OFF)
    await hass.async_block_till_done()
    assert controller.snapshot.state.value == GateState.OPENING.value

    hass.states.async_set("binary_sensor.gate_open", STATE_ON)
    await hass.async_block_till_done()
    assert controller.snapshot.state.value == GateState.OPEN.value
    assert controller.snapshot.estimated_position == 100

    hass.states.async_set("binary_sensor.gate_closed", STATE_ON)
    await hass.async_block_till_done()
    assert controller.snapshot.state.value == GateState.ERROR.value
    assert controller.snapshot.problem is GateProblem.LIMIT_SENSOR_CONFLICT
    problem = hass.states.get("binary_sensor.observed_gate_problem")
    assert problem is not None
    assert problem.state == STATE_ON

    with pytest.raises(ServiceValidationError):
        await controller.async_close()
    assert calls == []


async def test_unload_removes_source_listener_and_restore_never_replays_command(
    hass: HomeAssistant,
) -> None:
    calls: list[ServiceCall] = []

    async def record(call: ServiceCall) -> None:
        calls.append(call)

    hass.services.async_register("button", "press", record)
    hass.states.async_set("binary_sensor.gate_open", STATE_OFF)
    hass.states.async_set("binary_sensor.gate_closed", STATE_ON)
    hass.states.async_set("binary_sensor.gate_obstacle", STATE_OFF)
    entry = await setup_observed_gate(hass, observed_config())
    controller = entry.runtime_data.controller

    await controller.async_open()
    assert len(calls) == 1
    assert controller.snapshot.state is GateState.OPENING

    assert await hass.config_entries.async_unload(entry.entry_id)
    frozen = controller.snapshot
    hass.states.async_set("binary_sensor.gate_open", STATE_ON)
    await hass.async_block_till_done()
    assert controller.snapshot == frozen

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    restored = entry.runtime_data.controller.snapshot
    assert restored.state is GateState.ERROR
    assert restored.problem is GateProblem.LIMIT_SENSOR_CONFLICT
    assert len(calls) == 1


async def test_secondary_diagnostics_are_disabled_by_default(
    hass: HomeAssistant,
) -> None:
    hass.states.async_set("binary_sensor.gate_open", STATE_OFF)
    hass.states.async_set("binary_sensor.gate_closed", STATE_ON)
    hass.states.async_set("binary_sensor.gate_obstacle", STATE_OFF)
    entry = await setup_observed_gate(hass, observed_config())
    registry = er.async_get(hass)

    detailed = registry.async_get("sensor.observed_gate_detailed_state")
    last_direction = registry.async_get("sensor.observed_gate_last_direction")
    last_command = registry.async_get("sensor.observed_gate_last_command")
    assert detailed is not None
    assert not detailed.disabled
    assert last_direction is not None
    assert last_direction.disabled
    assert last_command is not None
    assert last_command.disabled
    assert entry.runtime_data.controller.snapshot.state is GateState.CLOSED


async def test_debounce_rejects_bounce_and_inverted_limit_is_authoritative(
    hass: HomeAssistant,
) -> None:
    config = observed_config(debounce_ms=20)
    assert config.closed_limit is not None
    config = replace(
        config,
        closed_limit=GateLimitConfig(
            "binary_sensor.gate_closed",
            active_state=False,
            debounce_ms=20,
        ),
    )
    hass.states.async_set("binary_sensor.gate_open", STATE_OFF)
    hass.states.async_set("binary_sensor.gate_closed", STATE_ON)
    hass.states.async_set("binary_sensor.gate_obstacle", STATE_OFF)
    entry = await setup_observed_gate(hass, config)
    controller = entry.runtime_data.controller
    assert controller.snapshot.state.value == GateState.UNKNOWN.value

    hass.states.async_set("binary_sensor.gate_closed", STATE_OFF)
    await asyncio.sleep(0.005)
    hass.states.async_set("binary_sensor.gate_closed", STATE_ON)
    await asyncio.sleep(0.03)
    assert controller.snapshot.state.value == GateState.UNKNOWN.value

    hass.states.async_set("binary_sensor.gate_closed", STATE_OFF)
    await asyncio.sleep(0.03)
    assert controller.snapshot.state.value == GateState.CLOSED.value


async def test_startup_inactive_limit_does_not_infer_motion_or_start_timer(
    hass: HomeAssistant,
) -> None:
    calls: list[ServiceCall] = []

    async def record(call: ServiceCall) -> None:
        calls.append(call)

    hass.services.async_register("button", "press", record)
    hass.states.async_set("binary_sensor.gate_open", STATE_OFF)
    hass.states.async_set("binary_sensor.gate_closed", STATE_ON)
    hass.states.async_set("binary_sensor.gate_obstacle", STATE_OFF)
    entry = await setup_observed_gate(hass, observed_config())
    assert entry.runtime_data.controller.snapshot.state is GateState.CLOSED

    assert await hass.config_entries.async_unload(entry.entry_id)
    hass.states.async_set("binary_sensor.gate_closed", STATE_OFF)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    snapshot = entry.runtime_data.controller.snapshot
    assert snapshot.state is GateState.UNKNOWN
    assert snapshot.current_direction.value == "unknown"
    assert calls == []


async def test_control_and_sensor_availability_are_tracked_separately(
    hass: HomeAssistant,
) -> None:
    hass.states.async_set("binary_sensor.gate_open", STATE_OFF)
    hass.states.async_set("binary_sensor.gate_closed", STATE_ON)
    hass.states.async_set("binary_sensor.gate_obstacle", STATE_OFF)
    entry = await setup_observed_gate(hass, observed_config())
    controller = entry.runtime_data.controller
    assert controller.control_available
    assert controller.sensor_available

    hass.states.async_set("binary_sensor.gate_obstacle", STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    assert controller.control_available
    assert not controller.sensor_available

    hass.states.async_set("button.observed_gate", STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    assert not controller.control_available
    assert controller.snapshot.problem is GateProblem.SOURCE_UNAVAILABLE


@pytest.mark.parametrize("with_open_limit", [False, True])
async def test_runtime_timeout_requires_configured_endpoint_confirmation(
    hass: HomeAssistant,
    with_open_limit: bool,
) -> None:
    """Real HA timer completes only unobserved endpoints and faults observed ones."""
    hass.services.async_register("button", "press", lambda call: None)
    hass.states.async_set("button.timer_gate", STATE_OFF)
    if with_open_limit:
        hass.states.async_set("binary_sensor.timer_open", STATE_OFF)
    config = GateConfig(
        device_id=f"timer-{with_open_limit}",
        name=f"Timer Gate {with_open_limit}",
        control_mode=ControlMode.SINGLE_STEP,
        step_source=SourceRef("button.timer_gate", ControlActionType.BUTTON),
        open_limit=GateLimitConfig("binary_sensor.timer_open", debounce_ms=0)
        if with_open_limit
        else None,
        opening_time_ms=10,
        opening_margin_ms=10,
        minimum_command_interval_ms=0,
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=config.name,
        unique_id=config.device_id,
        data=config.to_dict(),
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await entry.runtime_data.controller.async_open()
    await asyncio.sleep(0.04)

    snapshot = entry.runtime_data.controller.snapshot
    if with_open_limit:
        assert snapshot.state is GateState.ERROR
        assert snapshot.problem is GateProblem.OPENING_TIMEOUT
    else:
        assert snapshot.state is GateState.OPEN
        assert snapshot.estimated_position == 100


async def test_active_obstacle_blocks_close_without_physical_action(
    hass: HomeAssistant,
) -> None:
    calls: list[ServiceCall] = []

    async def record(call: ServiceCall) -> None:
        calls.append(call)

    hass.services.async_register("button", "press", record)
    hass.states.async_set("binary_sensor.gate_open", STATE_ON)
    hass.states.async_set("binary_sensor.gate_closed", STATE_OFF)
    hass.states.async_set("binary_sensor.gate_obstacle", STATE_ON)
    entry = await setup_observed_gate(hass, observed_config())
    controller = entry.runtime_data.controller
    assert controller.snapshot.state is GateState.OPEN
    assert controller.snapshot.problem is GateProblem.OBSTACLE

    with pytest.raises(ServiceValidationError):
        await controller.async_close()
    assert calls == []

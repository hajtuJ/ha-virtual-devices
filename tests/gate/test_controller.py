"""Safety and orchestration tests for GateController."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest
from custom_components.virtual_devices.gate import (
    ControlActionType,
    ControlMode,
    GateCommand,
    GateConfig,
    GateController,
    GateDirection,
    GateSnapshot,
    GateState,
    SourceRef,
    StopStrategyType,
)
from homeassistant.exceptions import ServiceValidationError


@dataclass
class FakeActions:
    """Record physical actions and allow deterministic blocking."""

    available: bool = True
    calls: list[tuple[str, str]] = field(default_factory=list)
    activated: asyncio.Event = field(default_factory=asyncio.Event)

    async def async_is_available(self, source: SourceRef) -> bool:
        del source
        return self.available

    async def async_activate(self, source: SourceRef) -> None:
        self.calls.append(("activate", source.entity_id))
        self.activated.set()

    async def async_deactivate(self, source: SourceRef) -> None:
        self.calls.append(("deactivate", source.entity_id))

    async def async_press(self, source: SourceRef) -> None:
        self.calls.append(("press", source.entity_id))


def button_config(**changes: object) -> GateConfig:
    """Return a fast valid single-button configuration."""
    values: dict[str, object] = {
        "device_id": "gate-id",
        "name": "Gate",
        "control_mode": ControlMode.SINGLE_STEP,
        "step_source": SourceRef("button.gate", ControlActionType.BUTTON),
        "minimum_command_interval_ms": 0,
    }
    values.update(changes)
    return GateConfig(**values)  # type: ignore[arg-type]


async def test_controller_commits_state_only_after_successful_action() -> None:
    actions = FakeActions()
    controller = GateController(
        button_config(),
        actions,
        initial_snapshot=GateSnapshot(state=GateState.CLOSED, estimated_position=0),
    )
    updates = 0

    def updated() -> None:
        nonlocal updates
        updates += 1

    controller.async_add_update_callback(updated)
    await controller.async_open()

    assert actions.calls == [("press", "button.gate")]
    assert controller.snapshot.state is GateState.OPENING
    assert controller.snapshot.last_command is GateCommand.OPEN
    assert updates == 1


async def test_unavailable_source_rejects_without_state_or_action() -> None:
    actions = FakeActions(available=False)
    original = GateSnapshot(state=GateState.CLOSED, estimated_position=0)
    controller = GateController(button_config(), actions, initial_snapshot=original)

    with pytest.raises(ServiceValidationError):
        await controller.async_open()

    assert actions.calls == []
    assert controller.snapshot.state is GateState.CLOSED
    assert not controller.snapshot.source_available


async def test_shutdown_cancels_pulse_and_waits_for_relay_cleanup() -> None:
    switch = SourceRef("switch.gate", ControlActionType.SWITCH)
    config = GateConfig(
        device_id="gate-id",
        name="Gate",
        control_mode=ControlMode.SINGLE_STEP,
        step_source=switch,
        pulse_duration_ms=60_000,
        minimum_command_interval_ms=0,
    )
    actions = FakeActions()
    controller = GateController(
        config,
        actions,
        initial_snapshot=GateSnapshot(state=GateState.CLOSED, estimated_position=0),
    )

    command = asyncio.create_task(controller.async_open())
    await actions.activated.wait()
    await controller.async_shutdown()

    with pytest.raises(asyncio.CancelledError):
        await command
    assert actions.calls == [
        ("activate", "switch.gate"),
        ("deactivate", "switch.gate"),
    ]
    assert controller.snapshot.state is GateState.CLOSED


async def test_configured_same_direction_stop_uses_direction_memory() -> None:
    config = button_config(stop_strategy=StopStrategyType.PULSE_SAME_DIRECTION)
    actions = FakeActions()
    controller = GateController(
        config,
        actions,
        initial_snapshot=GateSnapshot(
            state=GateState.OPENING,
            current_direction=GateDirection.OPENING,
            last_direction=GateDirection.OPENING,
        ),
    )

    await controller.async_stop()

    assert actions.calls == [("press", "button.gate")]
    assert controller.snapshot.state is GateState.STOPPED
    assert controller.snapshot.last_direction is GateDirection.OPENING

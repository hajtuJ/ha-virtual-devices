"""Safety and orchestration tests for GateController."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest
from custom_components.virtual_devices.gate import (
    ControlActionType,
    ControlMode,
    DirectionChangeStrategyType,
    GateCommand,
    GateConfig,
    GateController,
    GateDirection,
    GateEffectType,
    GateEndpoint,
    GateEvent,
    GateEventType,
    GateLimitConfig,
    GatePositionEstimator,
    GateProblem,
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
    availability: list[bool] = field(default_factory=list)
    calls: list[tuple[str, str]] = field(default_factory=list)
    activated: asyncio.Event = field(default_factory=asyncio.Event)
    pressed: asyncio.Event = field(default_factory=asyncio.Event)
    fail_press_number: int | None = None
    press_attempts: int = 0

    async def async_is_available(self, source: SourceRef) -> bool:
        del source
        return self.availability.pop(0) if self.availability else self.available

    async def async_activate(self, source: SourceRef) -> None:
        self.calls.append(("activate", source.entity_id))
        self.activated.set()

    async def async_deactivate(self, source: SourceRef) -> None:
        self.calls.append(("deactivate", source.entity_id))

    async def async_press(self, source: SourceRef) -> None:
        self.press_attempts += 1
        self.calls.append(("press", source.entity_id))
        self.pressed.set()
        if self.press_attempts == self.fail_press_number:
            raise RuntimeError("press failed")


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


def asymmetric_config(
    action_type: ControlActionType = ControlActionType.BUTTON,
    **changes: object,
) -> GateConfig:
    """Return the fixed asymmetric profile with its required CLOSED limit."""
    entity_id = f"{action_type.value}.gate"
    values: dict[str, object] = {
        "device_id": "asymmetric-gate-id",
        "name": "Asymmetric Gate",
        "control_mode": ControlMode.ASYMMETRIC_SINGLE_STEP,
        "step_source": SourceRef(entity_id, action_type),
        "closed_limit": GateLimitConfig("binary_sensor.gate_closed"),
        "pulse_duration_ms": 1,
        "pulse_interval_ms": 1,
        "minimum_command_interval_ms": 0,
    }
    values.update(changes)
    return GateConfig(**values)  # type: ignore[arg-type]


def symmetric_config(
    action_type: ControlActionType = ControlActionType.BUTTON,
    **changes: object,
) -> GateConfig:
    """Return the fixed symmetric single-source profile."""
    entity_id = f"{action_type.value}.gate"
    values: dict[str, object] = {
        "device_id": "symmetric-gate-id",
        "name": "Symmetric Gate",
        "control_mode": ControlMode.SYMMETRIC_SINGLE_STEP,
        "step_source": SourceRef(entity_id, action_type),
        "pulse_duration_ms": 1,
        "pulse_interval_ms": 1,
        "pulse_count": 3,
        "minimum_command_interval_ms": 0,
    }
    values.update(changes)
    return GateConfig(**values)  # type: ignore[arg-type]


@dataclass
class FakeClock:
    """Controllable estimator clock."""

    now: float = 0

    def monotonic(self) -> float:
        return self.now


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


async def test_controller_estimates_and_freezes_position_on_stop() -> None:
    config = button_config(
        opening_time_ms=10_000,
        closing_time_ms=20_000,
        stop_strategy=StopStrategyType.PULSE_SAME_DIRECTION,
    )
    clock = FakeClock()
    estimator = GatePositionEstimator(
        config.opening_time_ms,
        config.closing_time_ms,
        monotonic=clock.monotonic,
    )
    controller = GateController(
        config,
        FakeActions(),
        initial_snapshot=GateSnapshot(state=GateState.CLOSED, estimated_position=0),
        position_estimator=estimator,
    )

    await controller.async_open()
    clock.now = 5
    await controller.async_handle_event(GateEvent(GateEventType.MOVEMENT_TIMER_TICK))
    assert controller.snapshot.estimated_position == pytest.approx(50)

    await controller.async_stop()
    clock.now = 8
    assert controller.snapshot.state is GateState.STOPPED
    assert controller.snapshot.estimated_position == pytest.approx(50)


@pytest.mark.parametrize(
    ("strategy", "pulse_count", "expected_presses"),
    [
        (DirectionChangeStrategyType.DIRECT, 2, 1),
        (DirectionChangeStrategyType.STOP_WAIT_REVERSE, 2, 2),
        (DirectionChangeStrategyType.MULTI_PULSE, 3, 3),
    ],
)
async def test_controller_executes_configured_reversal_sequence(
    strategy: DirectionChangeStrategyType,
    pulse_count: int,
    expected_presses: int,
) -> None:
    """Controller translation preserves explicit reversal strategy semantics."""
    if strategy is DirectionChangeStrategyType.DIRECT:
        config = GateConfig(
            device_id="gate-id",
            name="Gate",
            control_mode=ControlMode.SEPARATE_OPEN_CLOSE,
            open_source=SourceRef("button.gate_open", ControlActionType.BUTTON),
            close_source=SourceRef("button.gate_close", ControlActionType.BUTTON),
            direction_change_strategy=strategy,
            minimum_command_interval_ms=0,
        )
    else:
        config = button_config(
            stop_strategy=StopStrategyType.PULSE_SAME_DIRECTION,
            direction_change_strategy=strategy,
            direction_change_delay_ms=1,
            pulse_interval_ms=1,
            pulse_count=pulse_count,
        )
    actions = FakeActions()
    controller = GateController(
        config,
        actions,
        initial_snapshot=GateSnapshot(
            state=GateState.OPENING,
            current_direction=GateDirection.OPENING,
            last_direction=GateDirection.OPENING,
            estimated_position=40,
        ),
    )

    await controller.async_close()

    assert controller.snapshot.state is GateState.CLOSING
    assert len(actions.calls) == expected_presses
    assert all(action == "press" for action, _entity_id in actions.calls)


@pytest.mark.parametrize(
    ("initial", "command", "expected_presses", "expected_state"),
    [
        (
            GateSnapshot(state=GateState.CLOSED, estimated_position=0),
            GateCommand.OPEN,
            1,
            GateState.OPENING,
        ),
        (
            GateSnapshot(state=GateState.OPEN, estimated_position=100),
            GateCommand.CLOSE,
            1,
            GateState.CLOSING,
        ),
        (
            GateSnapshot(
                state=GateState.OPENING,
                current_direction=GateDirection.OPENING,
                last_direction=GateDirection.OPENING,
            ),
            GateCommand.CLOSE,
            2,
            GateState.CLOSING,
        ),
        (
            GateSnapshot(
                state=GateState.CLOSING,
                current_direction=GateDirection.CLOSING,
                last_direction=GateDirection.CLOSING,
            ),
            GateCommand.OPEN,
            2,
            GateState.OPENING,
        ),
        (
            GateSnapshot(
                state=GateState.STOPPED,
                last_direction=GateDirection.OPENING,
            ),
            GateCommand.CLOSE,
            1,
            GateState.CLOSING,
        ),
        (
            GateSnapshot(
                state=GateState.STOPPED,
                last_direction=GateDirection.OPENING,
            ),
            GateCommand.OPEN,
            3,
            GateState.OPENING,
        ),
        (
            GateSnapshot(
                state=GateState.STOPPED,
                last_direction=GateDirection.CLOSING,
            ),
            GateCommand.OPEN,
            1,
            GateState.OPENING,
        ),
        (
            GateSnapshot(
                state=GateState.STOPPED,
                last_direction=GateDirection.CLOSING,
            ),
            GateCommand.CLOSE,
            3,
            GateState.CLOSING,
        ),
    ],
)
async def test_symmetric_button_profile_executes_one_command_sequence(
    initial: GateSnapshot,
    command: GateCommand,
    expected_presses: int,
    expected_state: GateState,
) -> None:
    """A single semantic command emits the full 1/2/3-pulse physical sequence."""
    actions = FakeActions()
    controller = GateController(
        symmetric_config(pulse_interval_ms=0),
        actions,
        initial_snapshot=initial,
    )

    await controller.async_command(command)

    assert actions.calls == [("press", "button.gate")] * expected_presses
    assert controller.snapshot.state is expected_state


@pytest.mark.parametrize(
    ("state", "direction"),
    [
        (GateState.OPENING, GateDirection.OPENING),
        (GateState.CLOSING, GateDirection.CLOSING),
    ],
)
async def test_symmetric_stop_executes_one_pulse_in_both_directions(
    state: GateState, direction: GateDirection
) -> None:
    actions = FakeActions()
    controller = GateController(
        symmetric_config(),
        actions,
        initial_snapshot=GateSnapshot(
            state=state,
            current_direction=direction,
            last_direction=direction,
        ),
    )

    await controller.async_stop()

    assert actions.calls == [("press", "button.gate")]
    assert controller.snapshot.state is GateState.STOPPED
    assert controller.snapshot.last_direction is direction


async def test_symmetric_switch_triple_pulse_is_ordered_and_deactivated() -> None:
    actions = FakeActions()
    controller = GateController(
        symmetric_config(ControlActionType.SWITCH, pulse_interval_ms=0),
        actions,
        initial_snapshot=GateSnapshot(
            state=GateState.STOPPED,
            last_direction=GateDirection.OPENING,
        ),
    )

    await controller.async_open()

    assert actions.calls == [
        (action, "switch.gate")
        for _ in range(3)
        for action in ("activate", "deactivate")
    ]
    assert controller.snapshot.state is GateState.OPENING


async def test_symmetric_partial_sequence_failure_becomes_unknown() -> None:
    actions = FakeActions(fail_press_number=2)
    controller = GateController(
        symmetric_config(pulse_interval_ms=0),
        actions,
        initial_snapshot=GateSnapshot(
            state=GateState.CLOSING,
            current_direction=GateDirection.CLOSING,
            last_direction=GateDirection.CLOSING,
        ),
    )

    with pytest.raises(ServiceValidationError):
        await controller.async_open()

    assert actions.calls == [("press", "button.gate")] * 2
    assert controller.snapshot.state is GateState.UNKNOWN
    assert controller.snapshot.current_direction is GateDirection.UNKNOWN
    assert controller.snapshot.problem is GateProblem.COMMAND_SEQUENCE_FAILED


@pytest.mark.parametrize(
    ("initial", "command", "expected_presses", "expected_state"),
    [
        (
            GateSnapshot(state=GateState.CLOSED, estimated_position=0),
            GateCommand.OPEN,
            1,
            GateState.OPENING,
        ),
        (
            GateSnapshot(state=GateState.OPEN, estimated_position=100),
            GateCommand.CLOSE,
            1,
            GateState.CLOSING,
        ),
        (
            GateSnapshot(
                state=GateState.OPENING,
                current_direction=GateDirection.OPENING,
                last_direction=GateDirection.OPENING,
                estimated_position=40,
            ),
            GateCommand.CLOSE,
            2,
            GateState.CLOSING,
        ),
        (
            GateSnapshot(
                state=GateState.CLOSING,
                current_direction=GateDirection.CLOSING,
                last_direction=GateDirection.CLOSING,
                estimated_position=40,
            ),
            GateCommand.OPEN,
            1,
            GateState.OPENING,
        ),
        (
            GateSnapshot(
                state=GateState.STOPPED,
                last_direction=GateDirection.OPENING,
                estimated_position=40,
            ),
            GateCommand.OPEN,
            2,
            GateState.OPENING,
        ),
        (
            GateSnapshot(
                state=GateState.STOPPED,
                last_direction=GateDirection.OPENING,
                estimated_position=40,
            ),
            GateCommand.CLOSE,
            1,
            GateState.CLOSING,
        ),
    ],
)
async def test_asymmetric_button_profile_executes_exact_pulse_count(
    initial: GateSnapshot,
    command: GateCommand,
    expected_presses: int,
    expected_state: GateState,
) -> None:
    actions = FakeActions()
    controller = GateController(
        asymmetric_config(pulse_interval_ms=0),
        actions,
        initial_snapshot=initial,
    )

    await controller.async_command(command)

    assert actions.calls == [("press", "button.gate")] * expected_presses
    assert controller.snapshot.state is expected_state


async def test_asymmetric_switch_double_pulse_is_ordered_and_deactivated() -> None:
    actions = FakeActions()
    controller = GateController(
        asymmetric_config(ControlActionType.SWITCH, pulse_interval_ms=0),
        actions,
        initial_snapshot=GateSnapshot(
            state=GateState.OPENING,
            current_direction=GateDirection.OPENING,
            last_direction=GateDirection.OPENING,
        ),
    )

    await controller.async_close()

    assert actions.calls == [
        ("activate", "switch.gate"),
        ("deactivate", "switch.gate"),
        ("activate", "switch.gate"),
        ("deactivate", "switch.gate"),
    ]
    assert controller.snapshot.state is GateState.CLOSING


async def test_asymmetric_double_pulse_uses_configured_interval() -> None:
    controller = GateController(
        asymmetric_config(pulse_interval_ms=725),
        FakeActions(),
        initial_snapshot=GateSnapshot(
            state=GateState.OPENING,
            current_direction=GateDirection.OPENING,
            last_direction=GateDirection.OPENING,
        ),
    )
    transition = controller._machine.transition(
        controller.snapshot, GateEvent(GateEventType.COMMAND_CLOSE)
    )
    command_effects = tuple(
        effect
        for effect in transition.effects
        if effect.type is GateEffectType.EXECUTE_STEP_PULSES
    )
    sequence = controller._sequence_for_effects(command_effects, controller.snapshot)

    assert [step.type.value for step in sequence.steps] == [
        "press",
        "delay",
        "press",
    ]
    assert sequence.steps[1].duration_ms == 725


async def test_asymmetric_stop_is_rejected_while_closing_without_action() -> None:
    actions = FakeActions()
    controller = GateController(
        asymmetric_config(),
        actions,
        initial_snapshot=GateSnapshot(
            state=GateState.CLOSING,
            current_direction=GateDirection.CLOSING,
            last_direction=GateDirection.CLOSING,
        ),
    )

    with pytest.raises(ServiceValidationError):
        await controller.async_stop()

    assert actions.calls == []
    assert controller.snapshot.state is GateState.CLOSING


@pytest.mark.parametrize(
    "snapshot",
    [
        GateSnapshot(),
        GateSnapshot(state=GateState.UNKNOWN_MOVING),
        GateSnapshot(state=GateState.STOPPED),
    ],
)
async def test_asymmetric_unknown_phase_is_rejected_without_action(
    snapshot: GateSnapshot,
) -> None:
    actions = FakeActions()
    controller = GateController(asymmetric_config(), actions, initial_snapshot=snapshot)

    with pytest.raises(ServiceValidationError):
        await controller.async_open()

    assert actions.calls == []
    assert controller.snapshot == snapshot


async def test_asymmetric_partial_sequence_failure_becomes_unknown() -> None:
    actions = FakeActions(availability=[True, True, True, False])
    controller = GateController(
        asymmetric_config(pulse_interval_ms=0),
        actions,
        initial_snapshot=GateSnapshot(
            state=GateState.OPENING,
            current_direction=GateDirection.OPENING,
            last_direction=GateDirection.OPENING,
            estimated_position=40,
        ),
    )

    with pytest.raises(ServiceValidationError):
        await controller.async_close()

    assert actions.calls == [("press", "button.gate")]
    assert controller.snapshot.state is GateState.UNKNOWN
    assert controller.snapshot.current_direction is GateDirection.UNKNOWN
    assert controller.snapshot.problem is GateProblem.SOURCE_UNAVAILABLE
    assert controller.snapshot.last_command is GateCommand.CLOSE

    await controller.async_handle_limit(GateEndpoint.CLOSED, raw_is_on=True)
    recovered = controller.snapshot
    assert recovered.state is GateState.CLOSED
    assert recovered.problem is GateProblem.SOURCE_UNAVAILABLE
    await controller.async_handle_event(GateEvent(GateEventType.SOURCE_AVAILABLE))
    source_recovered = controller.snapshot
    assert source_recovered.problem is GateProblem.NONE


async def test_asymmetric_action_exception_becomes_sequence_failure() -> None:
    actions = FakeActions(fail_press_number=2)
    controller = GateController(
        asymmetric_config(pulse_interval_ms=0),
        actions,
        initial_snapshot=GateSnapshot(
            state=GateState.OPENING,
            current_direction=GateDirection.OPENING,
            last_direction=GateDirection.OPENING,
            estimated_position=40,
        ),
    )

    with pytest.raises(ServiceValidationError):
        await controller.async_close()

    assert actions.calls == [("press", "button.gate")] * 2
    assert controller.snapshot.state is GateState.UNKNOWN
    assert controller.snapshot.problem is GateProblem.COMMAND_SEQUENCE_FAILED


async def test_asymmetric_preflight_failure_preserves_known_state() -> None:
    actions = FakeActions(available=False)
    original = GateSnapshot(state=GateState.CLOSED, estimated_position=0)
    controller = GateController(asymmetric_config(), actions, initial_snapshot=original)

    with pytest.raises(ServiceValidationError):
        await controller.async_open()

    assert actions.calls == []
    assert controller.snapshot.state is GateState.CLOSED
    assert controller.snapshot.problem is GateProblem.SOURCE_UNAVAILABLE


async def test_asymmetric_shutdown_after_first_pulse_marks_state_unknown() -> None:
    actions = FakeActions()
    controller = GateController(
        asymmetric_config(pulse_interval_ms=60_000),
        actions,
        initial_snapshot=GateSnapshot(
            state=GateState.OPENING,
            current_direction=GateDirection.OPENING,
            last_direction=GateDirection.OPENING,
            estimated_position=40,
        ),
    )

    command = asyncio.create_task(controller.async_close())
    await actions.pressed.wait()
    await controller.async_shutdown()

    with pytest.raises(asyncio.CancelledError):
        await command
    assert actions.calls == [("press", "button.gate")]
    assert controller.snapshot.state is GateState.UNKNOWN
    assert controller.snapshot.problem is GateProblem.COMMAND_SEQUENCE_FAILED


async def test_asymmetric_switch_cancellation_deactivates_relay_and_is_unknown() -> (
    None
):
    actions = FakeActions()
    controller = GateController(
        asymmetric_config(
            ControlActionType.SWITCH,
            pulse_duration_ms=60_000,
            pulse_interval_ms=0,
        ),
        actions,
        initial_snapshot=GateSnapshot(
            state=GateState.OPENING,
            current_direction=GateDirection.OPENING,
            last_direction=GateDirection.OPENING,
        ),
    )

    command = asyncio.create_task(controller.async_close())
    await actions.activated.wait()
    await controller.async_shutdown()

    with pytest.raises(asyncio.CancelledError):
        await command
    assert actions.calls == [
        ("activate", "switch.gate"),
        ("deactivate", "switch.gate"),
    ]
    assert controller.snapshot.state is GateState.UNKNOWN
    assert controller.snapshot.problem is GateProblem.COMMAND_SEQUENCE_FAILED

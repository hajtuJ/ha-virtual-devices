"""Safety-focused tests for the pure Virtual Gate state machine."""

import pytest
from custom_components.virtual_devices.gate import (
    DirectionChangeStrategyType,
    GateCommand,
    GateDirection,
    GateEffectType,
    GateEndpoint,
    GateEvent,
    GateEventType,
    GateProblem,
    GateSnapshot,
    GateState,
    GateStateMachine,
    GateStateMachineConfig,
    GateTransition,
    LimitSensorConfig,
    RepeatedCommandPolicy,
    StopStrategyType,
)


def effect_types(transition: GateTransition) -> tuple[GateEffectType, ...]:
    """Return effect types while retaining precise assertions at call sites."""
    return tuple(effect.type for effect in transition.effects)


@pytest.mark.parametrize(
    ("initial", "event_type", "expected_state", "expected_direction"),
    [
        (
            GateSnapshot(state=GateState.CLOSED, estimated_position=0),
            GateEventType.COMMAND_OPEN,
            GateState.OPENING,
            GateDirection.OPENING,
        ),
        (
            GateSnapshot(state=GateState.OPEN, estimated_position=100),
            GateEventType.COMMAND_CLOSE,
            GateState.CLOSING,
            GateDirection.CLOSING,
        ),
    ],
)
def test_normal_command_starts_motion(
    initial: GateSnapshot,
    event_type: GateEventType,
    expected_state: GateState,
    expected_direction: GateDirection,
) -> None:
    """A normal command changes state and emits execution plus timer effects."""
    result = GateStateMachine(GateStateMachineConfig()).transition(
        initial, GateEvent(event_type)
    )

    assert result.snapshot.state is expected_state
    assert result.snapshot.current_direction is expected_direction
    assert result.snapshot.last_direction is expected_direction
    assert effect_types(result) == (
        GateEffectType.EXECUTE_COMMAND,
        GateEffectType.START_MOVEMENT_TIMER,
        GateEffectType.STATE_CHANGED,
    )


@pytest.mark.parametrize(
    ("endpoint", "event_type", "start_state", "position"),
    [
        (GateEndpoint.OPEN, GateEventType.OPEN_LIMIT_ON, GateState.OPEN, 100),
        (GateEndpoint.CLOSED, GateEventType.CLOSED_LIMIT_ON, GateState.CLOSED, 0),
    ],
)
def test_endpoint_sensor_has_physical_precedence(
    endpoint: GateEndpoint,
    event_type: GateEventType,
    start_state: GateState,
    position: int,
) -> None:
    """An endpoint sensor ends motion and determines exact position."""
    config = GateStateMachineConfig(
        open_limit=LimitSensorConfig(), closed_limit=LimitSensorConfig()
    )
    direction = (
        GateDirection.OPENING
        if endpoint is GateEndpoint.OPEN
        else GateDirection.CLOSING
    )
    moving = GateSnapshot(
        state=GateState.OPENING
        if direction is GateDirection.OPENING
        else GateState.CLOSING,
        current_direction=direction,
        last_direction=direction,
    )

    result = GateStateMachine(config).transition(moving, GateEvent(event_type))

    assert result.snapshot.state is start_state
    assert result.snapshot.estimated_position == position
    assert effect_types(result) == (
        GateEffectType.CANCEL_MOVEMENT_TIMER,
        GateEffectType.STATE_CHANGED,
    )


def test_stop_preserves_last_direction_and_position() -> None:
    """STOP never discards the movement direction or estimated position."""
    machine = GateStateMachine(
        GateStateMachineConfig(stop_strategy=StopStrategyType.DEDICATED)
    )
    moving = GateSnapshot(
        state=GateState.OPENING,
        current_direction=GateDirection.OPENING,
        last_direction=GateDirection.OPENING,
        estimated_position=42,
    )

    result = machine.transition(moving, GateEvent(GateEventType.COMMAND_STOP))

    assert result.snapshot.state is GateState.STOPPED
    assert result.snapshot.current_direction is GateDirection.UNKNOWN
    assert result.snapshot.last_direction is GateDirection.OPENING
    assert result.snapshot.estimated_position == 42
    assert result.snapshot.last_command is GateCommand.STOP
    assert effect_types(result) == (
        GateEffectType.EXECUTE_STOP_STRATEGY,
        GateEffectType.CANCEL_MOVEMENT_TIMER,
        GateEffectType.STATE_CHANGED,
    )


def test_unsupported_stop_is_not_assumed() -> None:
    """No STOP effect or logical stop is invented without a strategy."""
    moving = GateSnapshot(
        state=GateState.CLOSING,
        current_direction=GateDirection.CLOSING,
        last_direction=GateDirection.CLOSING,
    )
    result = GateStateMachine(GateStateMachineConfig()).transition(
        moving, GateEvent(GateEventType.COMMAND_STOP)
    )
    assert result.snapshot == moving
    assert result.effects == ()


@pytest.mark.parametrize(
    "strategy",
    [
        DirectionChangeStrategyType.DIRECT,
        DirectionChangeStrategyType.STOP_THEN_REVERSE,
        DirectionChangeStrategyType.STOP_WAIT_REVERSE,
        DirectionChangeStrategyType.MULTI_PULSE,
        DirectionChangeStrategyType.CUSTOM_SEQUENCE,
    ],
)
def test_direction_reversal_uses_explicit_strategy(
    strategy: DirectionChangeStrategyType,
) -> None:
    """A reversal is represented by its configured strategy effect."""
    machine = GateStateMachine(
        GateStateMachineConfig(direction_change_strategy=strategy)
    )
    closing = GateSnapshot(
        state=GateState.CLOSING,
        current_direction=GateDirection.CLOSING,
        last_direction=GateDirection.CLOSING,
    )
    result = machine.transition(closing, GateEvent(GateEventType.COMMAND_OPEN))

    assert result.snapshot.state is GateState.OPENING
    assert result.effects[0].strategy is strategy
    assert effect_types(result) == (
        GateEffectType.EXECUTE_DIRECTION_CHANGE_STRATEGY,
        GateEffectType.CANCEL_MOVEMENT_TIMER,
        GateEffectType.START_MOVEMENT_TIMER,
        GateEffectType.STATE_CHANGED,
    )


def test_unsupported_direction_reversal_is_ignored() -> None:
    """A moving gate is unchanged if reversal behavior is unknown."""
    closing = GateSnapshot(
        state=GateState.CLOSING,
        current_direction=GateDirection.CLOSING,
    )
    result = GateStateMachine(GateStateMachineConfig()).transition(
        closing, GateEvent(GateEventType.COMMAND_OPEN)
    )
    assert result.snapshot == closing
    assert result.effects == ()


@pytest.mark.parametrize(
    "policy",
    [RepeatedCommandPolicy.REPEAT, RepeatedCommandPolicy.CUSTOM_SEQUENCE],
)
def test_repeated_command_emits_configured_policy(
    policy: RepeatedCommandPolicy,
) -> None:
    """Non-default repeated commands are explicit executor effects."""
    machine = GateStateMachine(GateStateMachineConfig(repeated_open_policy=policy))
    opening = GateSnapshot(
        state=GateState.OPENING,
        current_direction=GateDirection.OPENING,
    )
    result = machine.transition(opening, GateEvent(GateEventType.COMMAND_OPEN))
    assert result.effects[0].strategy is policy
    assert effect_types(result) == (
        GateEffectType.EXECUTE_REPEATED_COMMAND_POLICY,
        GateEffectType.STATE_CHANGED,
    )


def test_repeated_command_safe_defaults_to_ignore() -> None:
    """The default repeated-command policy performs no physical action."""
    opened = GateSnapshot(state=GateState.OPEN, estimated_position=100)
    result = GateStateMachine(GateStateMachineConfig()).transition(
        opened, GateEvent(GateEventType.COMMAND_OPEN)
    )
    assert result.snapshot == opened
    assert result.effects == ()


@pytest.mark.parametrize(
    ("has_target_limit", "state", "direction", "endpoint", "problem"),
    [
        (
            False,
            GateState.OPENING,
            GateDirection.OPENING,
            GateState.OPEN,
            GateProblem.NONE,
        ),
        (
            False,
            GateState.CLOSING,
            GateDirection.CLOSING,
            GateState.CLOSED,
            GateProblem.NONE,
        ),
        (
            True,
            GateState.OPENING,
            GateDirection.OPENING,
            GateState.ERROR,
            GateProblem.OPENING_TIMEOUT,
        ),
        (
            True,
            GateState.CLOSING,
            GateDirection.CLOSING,
            GateState.ERROR,
            GateProblem.CLOSING_TIMEOUT,
        ),
    ],
)
def test_timeout_never_fakes_a_configured_endpoint(
    has_target_limit: bool,
    state: GateState,
    direction: GateDirection,
    endpoint: GateState,
    problem: GateProblem,
) -> None:
    """Time may complete travel only when that endpoint has no sensor."""
    config = GateStateMachineConfig(
        open_limit=LimitSensorConfig()
        if has_target_limit and state is GateState.OPENING
        else None,
        closed_limit=LimitSensorConfig()
        if has_target_limit and state is GateState.CLOSING
        else None,
    )
    moving = GateSnapshot(state=state, current_direction=direction)
    result = GateStateMachine(config).transition(
        moving, GateEvent(GateEventType.MOVEMENT_TIMEOUT)
    )
    assert result.snapshot.state is endpoint
    assert result.snapshot.problem is problem


def test_active_state_inversion_is_normalized() -> None:
    """A normally-closed raw sensor maps to semantic endpoint events."""
    machine = GateStateMachine(
        GateStateMachineConfig(open_limit=LimitSensorConfig(active_state=False))
    )
    assert (
        machine.limit_event(GateEndpoint.OPEN, raw_is_on=False).type
        is GateEventType.OPEN_LIMIT_ON
    )
    assert (
        machine.limit_event(GateEndpoint.OPEN, raw_is_on=True).type
        is GateEventType.OPEN_LIMIT_OFF
    )


def test_limit_conflict_blocks_commands_and_resolves_to_remaining_endpoint() -> None:
    """Two active limits fault safely; the remaining physical limit wins."""
    machine = GateStateMachine(
        GateStateMachineConfig(
            open_limit=LimitSensorConfig(), closed_limit=LimitSensorConfig()
        )
    )
    open_snapshot = GateSnapshot(
        state=GateState.OPEN,
        estimated_position=100,
        open_limit_active=True,
    )
    conflict = machine.transition(
        open_snapshot, GateEvent(GateEventType.CLOSED_LIMIT_ON)
    ).snapshot
    assert conflict.state is GateState.ERROR
    assert conflict.problem is GateProblem.LIMIT_SENSOR_CONFLICT

    blocked = machine.transition(conflict, GateEvent(GateEventType.COMMAND_CLOSE))
    assert blocked.snapshot == conflict
    assert blocked.effects == ()

    resolved = machine.transition(conflict, GateEvent(GateEventType.OPEN_LIMIT_OFF))
    assert resolved.snapshot.state is GateState.CLOSED
    assert resolved.snapshot.estimated_position == 0
    assert resolved.snapshot.problem is GateProblem.NONE


@pytest.mark.parametrize(
    ("state", "limit_off", "expected_state", "direction"),
    [
        (
            GateState.CLOSED,
            GateEventType.CLOSED_LIMIT_OFF,
            GateState.OPENING,
            GateDirection.OPENING,
        ),
        (
            GateState.OPEN,
            GateEventType.OPEN_LIMIT_OFF,
            GateState.CLOSING,
            GateDirection.CLOSING,
        ),
    ],
)
def test_limit_release_infers_external_motion_without_physical_command(
    state: GateState,
    limit_off: GateEventType,
    expected_state: GateState,
    direction: GateDirection,
) -> None:
    """Leaving an endpoint starts observation, never a controller command."""
    config = GateStateMachineConfig(
        open_limit=LimitSensorConfig(), closed_limit=LimitSensorConfig()
    )
    initial = GateSnapshot(
        state=state,
        estimated_position=0 if state is GateState.CLOSED else 100,
        open_limit_active=state is GateState.OPEN,
        closed_limit_active=state is GateState.CLOSED,
    )
    result = GateStateMachine(config).transition(initial, GateEvent(limit_off))
    assert result.snapshot.state is expected_state
    assert result.snapshot.last_direction is direction
    assert GateEffectType.EXECUTE_COMMAND not in effect_types(result)


@pytest.mark.parametrize(
    "state",
    [GateState.OPENING, GateState.CLOSING, GateState.UNKNOWN_MOVING],
)
def test_restore_never_moves_and_reconciles_movement_to_stopped(
    state: GateState,
) -> None:
    """Restoring motion context is passive and preserves direction memory."""
    direction = (
        GateDirection.OPENING
        if state is GateState.OPENING
        else GateDirection.CLOSING
        if state is GateState.CLOSING
        else GateDirection.UNKNOWN
    )
    snapshot = GateSnapshot(
        state=state,
        current_direction=direction,
        last_direction=GateDirection.OPENING,
        estimated_position=33,
    )
    result = GateStateMachine(GateStateMachineConfig()).transition(
        snapshot, GateEvent(GateEventType.RESTORE)
    )
    assert result.snapshot.state is GateState.STOPPED
    assert result.snapshot.last_direction is GateDirection.OPENING
    assert all(not effect.type.value.startswith("execute") for effect in result.effects)


def test_restore_physical_limits_override_stored_state_without_commands() -> None:
    """Restore trusts sensors and emits notification effects only."""
    config = GateStateMachineConfig(
        open_limit=LimitSensorConfig(), closed_limit=LimitSensorConfig()
    )
    stored = GateSnapshot(
        state=GateState.OPEN,
        estimated_position=100,
        closed_limit_active=True,
    )
    result = GateStateMachine(config).transition(
        stored, GateEvent(GateEventType.RESTORE)
    )
    assert result.snapshot.state is GateState.CLOSED
    assert result.snapshot.estimated_position == 0
    assert effect_types(result) == (GateEffectType.STATE_CHANGED,)


def test_availability_and_obstacle_block_only_unsafe_commands() -> None:
    """Runtime safety inputs block physical effects without inventing motion."""
    machine = GateStateMachine(GateStateMachineConfig())
    unavailable = GateSnapshot(source_available=False)
    assert not machine.transition(
        unavailable, GateEvent(GateEventType.COMMAND_OPEN)
    ).effects

    obstructed = GateSnapshot(obstacle_active=True, problem=GateProblem.OBSTACLE)
    assert not machine.transition(
        obstructed, GateEvent(GateEventType.COMMAND_CLOSE)
    ).effects
    opening = machine.transition(obstructed, GateEvent(GateEventType.COMMAND_OPEN))
    assert opening.snapshot.state is GateState.OPENING

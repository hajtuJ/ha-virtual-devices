"""Tests for immutable gate domain models."""

from dataclasses import FrozenInstanceError

import pytest
from custom_components.virtual_devices.gate import (
    DirectionChangeStrategyType,
    GateCommand,
    GateDirection,
    GateEffect,
    GateEffectType,
    GateProblem,
    GateSnapshot,
    GateState,
    RepeatedCommandPolicy,
    StopStrategyType,
)


@pytest.mark.parametrize(
    ("state", "direction"),
    [
        (GateState.OPENING, GateDirection.OPENING),
        (GateState.CLOSING, GateDirection.CLOSING),
    ],
)
def test_moving_state_requires_matching_direction(
    state: GateState, direction: GateDirection
) -> None:
    """Test the moving-state direction invariant."""
    snapshot = GateSnapshot(state=state, current_direction=direction)
    assert snapshot.current_direction is direction

    with pytest.raises(ValueError, match="requires"):
        GateSnapshot(state=state, current_direction=GateDirection.UNKNOWN)


def test_stopped_snapshot_preserves_last_direction_and_position() -> None:
    """Test the mandatory direction-memory invariant after STOP."""
    snapshot = GateSnapshot(
        state=GateState.STOPPED,
        current_direction=GateDirection.UNKNOWN,
        last_direction=GateDirection.OPENING,
        estimated_position=47,
        last_command=GateCommand.STOP,
    )

    assert snapshot.last_direction is GateDirection.OPENING
    assert snapshot.estimated_position == 47


@pytest.mark.parametrize("position", [-0.1, 100.1])
def test_position_is_bounded(position: float) -> None:
    """Test rejection of an impossible estimated position."""
    with pytest.raises(ValueError, match="between 0 and 100"):
        GateSnapshot(estimated_position=position)


@pytest.mark.parametrize(
    ("state", "position"),
    [(GateState.CLOSED, 1), (GateState.OPEN, 99)],
)
def test_known_endpoint_position_must_match_state(
    state: GateState, position: float
) -> None:
    """Test endpoint state/position consistency."""
    with pytest.raises(ValueError, match="position must be"):
        GateSnapshot(state=state, estimated_position=position)


def test_domain_models_are_immutable() -> None:
    """Test that transitions cannot mutate an existing snapshot."""
    snapshot = GateSnapshot()
    with pytest.raises(FrozenInstanceError):
        snapshot.state = GateState.OPEN  # type: ignore[misc]


def test_effect_payload_is_validated() -> None:
    """Test command payload compatibility with effect type."""
    effect = GateEffect(GateEffectType.EXECUTE_COMMAND, GateCommand.OPEN)
    assert effect.command is GateCommand.OPEN

    with pytest.raises(ValueError, match="requires a command"):
        GateEffect(GateEffectType.EXECUTE_COMMAND)
    with pytest.raises(ValueError, match="only execute-command"):
        GateEffect(GateEffectType.STATE_CHANGED, GateCommand.CLOSE)


def test_strategy_enums_preserve_specification_values() -> None:
    """Test safety-relevant strategy values used in persisted configuration."""
    assert StopStrategyType.UNSUPPORTED.value == "unsupported"
    assert DirectionChangeStrategyType.STOP_WAIT_REVERSE.value == "stop_wait_reverse"
    assert RepeatedCommandPolicy.IGNORE.value == "ignore"
    assert GateProblem.LIMIT_SENSOR_CONFLICT.value == "limit_sensor_conflict"

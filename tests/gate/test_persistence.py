"""Tests for restart-safe semantic gate persistence."""

from custom_components.virtual_devices.gate import (
    GateCommand,
    GateDirection,
    GateSnapshot,
    GateState,
)
from custom_components.virtual_devices.gate.persistence import GateStoredState


def test_stored_state_round_trip_contains_no_executable_context() -> None:
    snapshot = GateSnapshot(
        state=GateState.OPENING,
        current_direction=GateDirection.OPENING,
        last_direction=GateDirection.OPENING,
        estimated_position=47,
        last_command=GateCommand.OPEN,
    )
    stored = GateStoredState.from_snapshot(snapshot)
    raw = stored.to_dict()

    assert set(raw) == {
        "state",
        "last_direction",
        "estimated_position",
        "last_command",
        "last_transition_timestamp",
    }
    restored = GateStoredState.from_dict(raw).to_snapshot()
    assert restored.state is GateState.OPENING
    assert restored.current_direction is GateDirection.OPENING
    assert restored.last_direction is GateDirection.OPENING
    assert restored.estimated_position == 47
    assert restored.last_command is GateCommand.OPEN

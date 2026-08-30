"""Tests for serializable gate command models."""

import pytest
from custom_components.virtual_devices.gate import (
    CommandSequence,
    CommandStep,
    CommandStepType,
    ControlActionType,
    SourceRef,
)


def test_command_sequence_round_trip() -> None:
    """Test a pulse-like sequence survives storage serialization."""
    source = SourceRef("switch.gate_open", ControlActionType.SWITCH)
    sequence = CommandSequence(
        name="open_pulse",
        steps=(
            CommandStep(CommandStepType.ACTIVATE, source=source),
            CommandStep(CommandStepType.DELAY, duration_ms=500),
            CommandStep(CommandStepType.DEACTIVATE, source=source),
        ),
    )

    assert CommandSequence.from_dict(sequence.to_dict()) == sequence


@pytest.mark.parametrize(
    ("entity_id", "action_type"),
    [
        ("gate_open", ControlActionType.SWITCH),
        ("button.gate_open", ControlActionType.SWITCH),
        ("switch.gate_open", ControlActionType.BUTTON),
    ],
)
def test_source_reference_rejects_invalid_identity(
    entity_id: str, action_type: ControlActionType
) -> None:
    """Test source/action domain consistency."""
    with pytest.raises(ValueError, match=r"domain|entity_id"):
        SourceRef(entity_id, action_type)


@pytest.mark.parametrize("duration", [None, 0, -1])
def test_delay_requires_positive_duration(duration: int | None) -> None:
    """Test delay timing validation."""
    with pytest.raises(ValueError, match="duration"):
        CommandStep(CommandStepType.DELAY, duration_ms=duration)


def test_switch_and_button_steps_are_not_interchangeable() -> None:
    """Test action types cannot call an incompatible HA source domain."""
    switch = SourceRef("switch.gate", ControlActionType.SWITCH)
    button = SourceRef("button.gate", ControlActionType.BUTTON)

    with pytest.raises(ValueError, match="switch source"):
        CommandStep(CommandStepType.ACTIVATE, source=button)
    with pytest.raises(ValueError, match="button source"):
        CommandStep(CommandStepType.PRESS, source=switch)


@pytest.mark.parametrize(
    ("name", "steps", "message"),
    [
        ("", (CommandStep(CommandStepType.DELAY, duration_ms=1),), "name"),
        ("empty", (), "at least one"),
    ],
)
def test_sequence_requires_name_and_steps(
    name: str, steps: tuple[CommandStep, ...], message: str
) -> None:
    """Test rejection of meaningless command sequences."""
    with pytest.raises(ValueError, match=message):
        CommandSequence(name=name, steps=steps)

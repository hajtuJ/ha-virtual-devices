"""Tests for versioned, serializable Virtual Gate configuration."""

import json
from dataclasses import replace
from typing import Any

import pytest
from custom_components.virtual_devices.gate import (
    CONFIG_VERSION,
    ControlActionType,
    ControlMode,
    DirectionChangeStrategyType,
    GateConfig,
    GateConfigError,
    GateLimitConfig,
    RepeatedCommandPolicy,
    SourceRef,
    StopStrategyType,
)


def source(entity_id: str) -> SourceRef:
    """Create a source whose action family matches its entity domain."""
    return SourceRef(entity_id, ControlActionType(entity_id.split(".", 1)[0]))


def single_step_config(**changes: Any) -> GateConfig:
    """Create one safe baseline configuration and apply typed test changes."""
    baseline = GateConfig(
        device_id="gate-1",
        name="Driveway Gate",
        control_mode=ControlMode.SINGLE_STEP,
        step_source=source("button.gate"),
    )
    return replace(baseline, **changes)


def test_configuration_round_trip_is_json_safe_and_versioned() -> None:
    """Persisted configuration restores every nested enum, source, and limit."""
    config = single_step_config(
        open_limit=GateLimitConfig(
            "binary_sensor.gate_open", active_state=False, debounce_ms=450
        ),
        closed_limit=GateLimitConfig("binary_sensor.gate_closed"),
        obstacle_source="binary_sensor.gate_obstacle",
        opening_time_ms=17000,
        closing_time_ms=19000,
        direction_change_strategy=DirectionChangeStrategyType.MULTI_PULSE,
        repeated_open_policy=RepeatedCommandPolicy.REPEAT,
    )

    serialized = config.to_dict()
    json.dumps(serialized)

    assert serialized["config_version"] == CONFIG_VERSION
    assert GateConfig.from_dict(serialized) == config


@pytest.mark.parametrize(
    ("mode", "kwargs"),
    [
        (
            ControlMode.SINGLE_STEP,
            {"step_source": source("button.gate")},
        ),
        (
            ControlMode.SEPARATE_OPEN_CLOSE,
            {
                "open_source": source("switch.gate_open"),
                "close_source": source("switch.gate_close"),
            },
        ),
        (
            ControlMode.SEPARATE_OPEN_CLOSE_STOP,
            {
                "open_source": source("switch.gate_open"),
                "close_source": source("switch.gate_close"),
                "stop_source": source("button.gate_stop"),
            },
        ),
    ],
)
def test_each_control_topology_is_valid(
    mode: ControlMode, kwargs: dict[str, Any]
) -> None:
    """The model supports all three agreed MVP controller layouts."""
    config = GateConfig(
        device_id="gate-1",
        name="Gate",
        control_mode=mode,
        **kwargs,
    )
    assert config.control_mode is mode


def test_control_mode_rejects_missing_and_extra_sources() -> None:
    """A mode cannot silently ignore or invent required physical controls."""
    with pytest.raises(GateConfigError, match="invalid_source_layout"):
        GateConfig(
            device_id="gate-1",
            name="Gate",
            control_mode=ControlMode.SINGLE_STEP,
            open_source=source("switch.gate_open"),
        )


def test_control_sources_must_be_mutually_distinct() -> None:
    """Separate OPEN and CLOSE outputs cannot point at the same relay."""
    duplicate = source("switch.gate")
    with pytest.raises(GateConfigError, match="duplicate_control_source"):
        GateConfig(
            device_id="gate-1",
            name="Gate",
            control_mode=ControlMode.SEPARATE_OPEN_CLOSE,
            open_source=duplicate,
            close_source=duplicate,
        )


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("opening_time_ms", 0, "positive"),
        ("closing_time_ms", -1, "positive"),
        ("pulse_duration_ms", 0, "positive"),
        ("hold_duration_ms", -1, "positive"),
        ("opening_margin_ms", -1, "non_negative"),
        ("minimum_command_interval_ms", -1, "non_negative"),
        ("pulse_interval_ms", -1, "non_negative"),
    ],
)
def test_timing_validation(field: str, value: int, error: str) -> None:
    """Travel, pulse, HOLD, margin, and interval bounds are enforced."""
    with pytest.raises(GateConfigError, match=error):
        single_step_config(**{field: value})


def test_limit_configuration_validates_domain_debounce_and_uniqueness() -> None:
    """Only distinct binary sensors with non-negative debounce are accepted."""
    with pytest.raises(GateConfigError, match="invalid_binary_sensor"):
        GateLimitConfig("sensor.gate")
    with pytest.raises(GateConfigError, match="non_negative"):
        GateLimitConfig("binary_sensor.gate", debounce_ms=-1)
    with pytest.raises(GateConfigError, match="duplicate_sensor"):
        single_step_config(
            open_limit=GateLimitConfig("binary_sensor.gate"),
            closed_limit=GateLimitConfig("binary_sensor.gate"),
        )


def test_dedicated_stop_requires_dedicated_source() -> None:
    """The model never advertises a dedicated STOP it cannot execute."""
    with pytest.raises(GateConfigError, match="dedicated_stop_required"):
        single_step_config(stop_strategy=StopStrategyType.DEDICATED)


def test_hold_strategy_requires_switch_direction_sources() -> None:
    """A button cannot be left active for bounded HOLD semantics."""
    with pytest.raises(GateConfigError, match="hold_requires_switch"):
        single_step_config(stop_strategy=StopStrategyType.HOLD_SAME_DIRECTION)


def test_stop_dependent_policies_require_stop_support() -> None:
    """Reversal and repeated STOP behavior cannot rely on an absent strategy."""
    with pytest.raises(GateConfigError, match="reversal_requires_stop"):
        single_step_config(
            direction_change_strategy=DirectionChangeStrategyType.STOP_WAIT_REVERSE
        )
    with pytest.raises(GateConfigError, match="repeated_stop_requires_stop"):
        single_step_config(repeated_open_policy=RepeatedCommandPolicy.STOP)


def test_multi_pulse_requires_at_least_two_pulses() -> None:
    """A one-pulse strategy cannot be persisted under a multi-pulse name."""
    with pytest.raises(GateConfigError, match="multi_pulse_requires_multiple"):
        single_step_config(
            direction_change_strategy=DirectionChangeStrategyType.MULTI_PULSE,
            pulse_count=1,
        )


def test_custom_sequences_are_rejected_until_the_ui_can_define_them() -> None:
    """The stored MVP model cannot contain an unrepresentable custom sequence."""
    with pytest.raises(GateConfigError, match="custom_sequence_not_supported"):
        single_step_config(stop_strategy=StopStrategyType.CUSTOM_SEQUENCE)


def test_configuration_requires_current_version_and_stable_identity() -> None:
    """Unknown schema versions and empty identities fail at the boundary."""
    with pytest.raises(GateConfigError, match="unsupported_version"):
        single_step_config(config_version=CONFIG_VERSION + 1)
    with pytest.raises(GateConfigError, match="required"):
        single_step_config(device_id="")

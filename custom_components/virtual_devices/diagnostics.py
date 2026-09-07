"""Redacted config-entry diagnostics for Virtual Devices."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .gate import ControlMode

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from . import VirtualDevicesConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: VirtualDevicesConfigEntry,
) -> dict[str, Any]:
    """Return useful runtime data without names or source entity IDs."""
    del hass
    runtime = entry.runtime_data
    config = runtime.config
    snapshot = runtime.controller.snapshot
    asymmetric = config.control_mode is ControlMode.ASYMMETRIC_SINGLE_STEP
    symmetric = config.control_mode is ControlMode.SYMMETRIC_SINGLE_STEP
    effective_behavior: dict[str, str | int] | None = None
    if asymmetric:
        effective_behavior = {
            "stop_while_opening": "one_pulse",
            "stop_while_closing": "unsupported",
            "opening_to_closing_pulses": 2,
            "closing_to_opening_pulses": 1,
        }
    elif symmetric:
        effective_behavior = {
            "stop_while_opening": "one_pulse",
            "stop_while_closing": "one_pulse",
            "opening_to_closing_pulses": 2,
            "closing_to_opening_pulses": 2,
            "stopped_same_direction_pulses": 3,
            "stopped_opposite_direction_pulses": 1,
        }
    return {
        "config": {
            "config_version": config.config_version,
            "control_mode": config.control_mode.value,
            "control_source_count": len(config.control_sources),
            "has_open_limit": config.open_limit is not None,
            "has_closed_limit": config.closed_limit is not None,
            "has_obstacle_source": config.obstacle_source is not None,
            "stop_strategy": config.stop_strategy.value,
            "direction_change_strategy": config.direction_change_strategy.value,
            "control_profile": (
                "asymmetric_single_step"
                if asymmetric
                else "symmetric_single_step"
                if symmetric
                else "configured_strategies"
            ),
            "effective_directional_behavior": effective_behavior,
            "opening_time_ms": config.opening_time_ms,
            "closing_time_ms": config.closing_time_ms,
            "opening_margin_ms": config.opening_margin_ms,
            "closing_margin_ms": config.closing_margin_ms,
        },
        "runtime": {
            "state": snapshot.state.value,
            "current_direction": snapshot.current_direction.value,
            "last_direction": snapshot.last_direction.value,
            "estimated_position": snapshot.estimated_position,
            "last_command": snapshot.last_command.value
            if snapshot.last_command is not None
            else None,
            "problem": snapshot.problem.value,
            "open_limit_active": snapshot.open_limit_active,
            "closed_limit_active": snapshot.closed_limit_active,
            "control_available": runtime.controller.control_available,
            "sensor_available": runtime.controller.sensor_available,
            "obstacle_active": snapshot.obstacle_active,
        },
    }

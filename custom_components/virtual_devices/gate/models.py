"""Immutable domain types for Virtual Gate."""

from dataclasses import dataclass
from enum import StrEnum


class GateState(StrEnum):
    """Logical state of a virtual gate."""

    UNKNOWN = "unknown"
    CLOSED = "closed"
    OPENING = "opening"
    OPEN = "open"
    CLOSING = "closing"
    STOPPED = "stopped"
    UNKNOWN_MOVING = "unknown_moving"
    ERROR = "error"


class GateDirection(StrEnum):
    """Known current or historical movement direction."""

    UNKNOWN = "unknown"
    OPENING = "opening"
    CLOSING = "closing"


class GateCommand(StrEnum):
    """Command requested from the virtual gate."""

    OPEN = "open"
    CLOSE = "close"
    STOP = "stop"


class GateProblem(StrEnum):
    """Problem currently affecting the virtual gate."""

    NONE = "none"
    OPENING_TIMEOUT = "opening_timeout"
    CLOSING_TIMEOUT = "closing_timeout"
    LIMIT_SENSOR_CONFLICT = "limit_sensor_conflict"
    SOURCE_UNAVAILABLE = "source_unavailable"
    OBSTACLE = "obstacle"


class ControlMode(StrEnum):
    """Physical controller layout used by a virtual gate."""

    SINGLE_STEP = "single_step"
    SEPARATE_OPEN_CLOSE = "separate_open_close"
    SEPARATE_OPEN_CLOSE_STOP = "separate_open_close_stop"


class ControlActionType(StrEnum):
    """MVP source entity action families."""

    SWITCH = "switch"
    BUTTON = "button"


class StopStrategyType(StrEnum):
    """Strategy used to stop a moving gate."""

    DEDICATED = "dedicated"
    PULSE_SAME_DIRECTION = "pulse_same_direction"
    PULSE_OPPOSITE_DIRECTION = "pulse_opposite_direction"
    HOLD_SAME_DIRECTION = "hold_same_direction"
    HOLD_OPPOSITE_DIRECTION = "hold_opposite_direction"
    CUSTOM_SEQUENCE = "custom_sequence"
    UNSUPPORTED = "unsupported"


class DirectionChangeStrategyType(StrEnum):
    """Strategy used when reversing a moving gate."""

    DIRECT = "direct"
    STOP_THEN_REVERSE = "stop_then_reverse"
    STOP_WAIT_REVERSE = "stop_wait_reverse"
    MULTI_PULSE = "multi_pulse"
    CUSTOM_SEQUENCE = "custom_sequence"
    UNSUPPORTED = "unsupported"


class RepeatedCommandPolicy(StrEnum):
    """Policy for a command matching the state or current direction."""

    IGNORE = "ignore"
    REPEAT = "repeat"
    STOP = "stop"
    CUSTOM_SEQUENCE = "custom_sequence"


class GateEventType(StrEnum):
    """Event accepted by the gate state machine."""

    COMMAND_OPEN = "command_open"
    COMMAND_CLOSE = "command_close"
    COMMAND_STOP = "command_stop"
    OPEN_LIMIT_ON = "open_limit_on"
    OPEN_LIMIT_OFF = "open_limit_off"
    CLOSED_LIMIT_ON = "closed_limit_on"
    CLOSED_LIMIT_OFF = "closed_limit_off"
    MOVEMENT_TIMER_TICK = "movement_timer_tick"
    MOVEMENT_TIMEOUT = "movement_timeout"
    SOURCE_AVAILABLE = "source_available"
    SOURCE_UNAVAILABLE = "source_unavailable"
    OBSTACLE_ON = "obstacle_on"
    OBSTACLE_OFF = "obstacle_off"
    RESTORE = "restore"
    CONFIG_CHANGED = "config_changed"


class GateEffectType(StrEnum):
    """Side effect requested by a pure state transition."""

    EXECUTE_COMMAND = "execute_command"
    START_MOVEMENT_TIMER = "start_movement_timer"
    CANCEL_MOVEMENT_TIMER = "cancel_movement_timer"
    STATE_CHANGED = "state_changed"


@dataclass(frozen=True, slots=True)
class GateEvent:
    """Input to the pure gate state machine."""

    type: GateEventType


@dataclass(frozen=True, slots=True)
class GateEffect:
    """Side effect emitted by the pure gate state machine."""

    type: GateEffectType
    command: GateCommand | None = None

    def __post_init__(self) -> None:
        """Validate effect payload compatibility."""
        if self.type is GateEffectType.EXECUTE_COMMAND and self.command is None:
            msg = "execute-command effect requires a command"
            raise ValueError(msg)
        if self.type is not GateEffectType.EXECUTE_COMMAND and self.command is not None:
            msg = "only execute-command effects may carry a command"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class GateSnapshot:
    """Complete immutable semantic state of one virtual gate."""

    state: GateState = GateState.UNKNOWN
    current_direction: GateDirection = GateDirection.UNKNOWN
    last_direction: GateDirection = GateDirection.UNKNOWN
    estimated_position: float | None = None
    problem: GateProblem = GateProblem.NONE
    last_command: GateCommand | None = None

    def __post_init__(self) -> None:
        """Enforce state invariants at the domain boundary."""
        position = self.estimated_position
        if position is not None and not 0 <= position <= 100:
            msg = "estimated_position must be between 0 and 100"
            raise ValueError(msg)

        expected_direction = {
            GateState.OPENING: GateDirection.OPENING,
            GateState.CLOSING: GateDirection.CLOSING,
        }.get(self.state)
        if (
            expected_direction is not None
            and self.current_direction is not expected_direction
        ):
            msg = f"{self.state.value} requires {expected_direction.value} direction"
            raise ValueError(msg)

        if (
            self.state is GateState.STOPPED
            and self.current_direction is not GateDirection.UNKNOWN
        ):
            msg = "stopped gate cannot have a current direction"
            raise ValueError(msg)

        if self.state is GateState.CLOSED and position not in (None, 0):
            msg = "closed gate position must be 0 when known"
            raise ValueError(msg)

        if self.state is GateState.OPEN and position not in (None, 100):
            msg = "open gate position must be 100 when known"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class GateTransition:
    """Result of applying one event to a gate snapshot."""

    snapshot: GateSnapshot
    effects: tuple[GateEffect, ...] = ()

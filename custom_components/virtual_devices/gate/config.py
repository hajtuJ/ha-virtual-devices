"""Versioned and storage-safe configuration for one Virtual Gate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Self

from ..const import (
    CONF_CLOSE_SOURCE,
    CONF_CLOSED_LIMIT,
    CONF_CLOSING_MARGIN_MS,
    CONF_CLOSING_TIME_MS,
    CONF_CONFIG_VERSION,
    CONF_CONTROL_MODE,
    CONF_DEVICE_ID,
    CONF_DIRECTION_CHANGE_DELAY_MS,
    CONF_DIRECTION_CHANGE_STRATEGY,
    CONF_HOLD_DURATION_MS,
    CONF_MINIMUM_COMMAND_INTERVAL_MS,
    CONF_OBSTACLE_SOURCE,
    CONF_OPEN_LIMIT,
    CONF_OPEN_SOURCE,
    CONF_OPENING_MARGIN_MS,
    CONF_OPENING_TIME_MS,
    CONF_PULSE_COUNT,
    CONF_PULSE_DURATION_MS,
    CONF_PULSE_INTERVAL_MS,
    CONF_REPEATED_CLOSE_POLICY,
    CONF_REPEATED_OPEN_POLICY,
    CONF_STEP_SOURCE,
    CONF_STOP_SOURCE,
    CONF_STOP_STRATEGY,
)
from .command_models import SourceRef
from .models import (
    ControlActionType,
    ControlMode,
    DirectionChangeStrategyType,
    RepeatedCommandPolicy,
    StopStrategyType,
)

CONFIG_VERSION = 1


class GateConfigError(ValueError):
    """Describe one user-correctable configuration error."""

    def __init__(self, field: str, code: str) -> None:
        """Initialize an error suitable for a Config Flow field mapping."""
        self.field = field
        self.code = code
        super().__init__(f"{field}: {code}")


@dataclass(frozen=True, slots=True)
class GateLimitConfig:
    """Configuration of one physical endpoint sensor."""

    entity_id: str
    active_state: bool = True
    debounce_ms: int = 300

    def __post_init__(self) -> None:
        """Validate endpoint identity and debounce timing."""
        if not self.entity_id.startswith("binary_sensor."):
            raise GateConfigError("limit", "invalid_binary_sensor")
        if self.debounce_ms < 0:
            raise GateConfigError("debounce_ms", "non_negative")

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe limit data."""
        return {
            "entity_id": self.entity_id,
            "active_state": self.active_state,
            "debounce_ms": self.debounce_ms,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        """Restore and validate a limit configuration."""
        return cls(
            entity_id=str(value["entity_id"]),
            active_state=bool(value["active_state"]),
            debounce_ms=int(value["debounce_ms"]),
        )


@dataclass(frozen=True, slots=True)
class GateConfig:
    """Complete versioned configuration of one independently managed gate."""

    device_id: str
    name: str
    control_mode: ControlMode
    step_source: SourceRef | None = None
    open_source: SourceRef | None = None
    close_source: SourceRef | None = None
    stop_source: SourceRef | None = None
    open_limit: GateLimitConfig | None = None
    closed_limit: GateLimitConfig | None = None
    obstacle_source: str | None = None
    opening_time_ms: int = 15000
    closing_time_ms: int = 15000
    opening_margin_ms: int = 2000
    closing_margin_ms: int = 2000
    pulse_duration_ms: int = 500
    hold_duration_ms: int = 2200
    minimum_command_interval_ms: int = 700
    direction_change_delay_ms: int = 800
    pulse_interval_ms: int = 700
    pulse_count: int = 2
    stop_strategy: StopStrategyType = StopStrategyType.UNSUPPORTED
    direction_change_strategy: DirectionChangeStrategyType = (
        DirectionChangeStrategyType.UNSUPPORTED
    )
    repeated_open_policy: RepeatedCommandPolicy = RepeatedCommandPolicy.IGNORE
    repeated_close_policy: RepeatedCommandPolicy = RepeatedCommandPolicy.IGNORE
    config_version: int = CONFIG_VERSION

    def __post_init__(self) -> None:
        """Validate the complete configuration as one safety boundary."""
        if self.config_version != CONFIG_VERSION:
            raise GateConfigError(CONF_CONFIG_VERSION, "unsupported_version")
        if not self.device_id or not self.name.strip():
            raise GateConfigError("name", "required")
        self._validate_sources()
        self._validate_sensors()
        self._validate_timings()
        self._validate_strategies()

    @property
    def control_sources(self) -> tuple[SourceRef, ...]:
        """Return configured physical controls in semantic order."""
        return tuple(
            source
            for source in (
                self.step_source,
                self.open_source,
                self.close_source,
                self.stop_source,
            )
            if source is not None
        )

    @property
    def source_signature(self) -> tuple[str, ...]:
        """Return a stable signature used to reject an accidental duplicate gate."""
        return tuple(sorted(source.entity_id for source in self.control_sources))

    def _validate_sources(self) -> None:
        """Enforce the selected controller topology and output uniqueness."""
        if self.control_mode is ControlMode.SINGLE_STEP:
            valid = self.step_source is not None and all(
                source is None
                for source in (self.open_source, self.close_source, self.stop_source)
            )
        elif self.control_mode is ControlMode.SEPARATE_OPEN_CLOSE:
            valid = (
                self.step_source is None
                and self.open_source is not None
                and self.close_source is not None
                and self.stop_source is None
            )
        else:
            valid = (
                self.step_source is None
                and self.open_source is not None
                and self.close_source is not None
                and self.stop_source is not None
            )
        if not valid:
            raise GateConfigError(CONF_CONTROL_MODE, "invalid_source_layout")

        entity_ids = [source.entity_id for source in self.control_sources]
        if len(entity_ids) != len(set(entity_ids)):
            raise GateConfigError(CONF_OPEN_SOURCE, "duplicate_control_source")

    def _validate_sensors(self) -> None:
        """Reject ambiguous limit and safety sensor assignments."""
        sensor_ids = [
            limit.entity_id
            for limit in (self.open_limit, self.closed_limit)
            if limit is not None
        ]
        if self.obstacle_source is not None:
            if not self.obstacle_source.startswith("binary_sensor."):
                raise GateConfigError(CONF_OBSTACLE_SOURCE, "invalid_binary_sensor")
            sensor_ids.append(self.obstacle_source)
        if len(sensor_ids) != len(set(sensor_ids)):
            raise GateConfigError(CONF_OPEN_LIMIT, "duplicate_sensor")

    def _validate_timings(self) -> None:
        """Validate travel, pulse, margin, debounce, and interval values."""
        positive = {
            CONF_OPENING_TIME_MS: self.opening_time_ms,
            CONF_CLOSING_TIME_MS: self.closing_time_ms,
            CONF_PULSE_DURATION_MS: self.pulse_duration_ms,
            CONF_HOLD_DURATION_MS: self.hold_duration_ms,
            CONF_PULSE_COUNT: self.pulse_count,
        }
        for field, value in positive.items():
            if value <= 0:
                raise GateConfigError(field, "positive")

        non_negative = {
            CONF_OPENING_MARGIN_MS: self.opening_margin_ms,
            CONF_CLOSING_MARGIN_MS: self.closing_margin_ms,
            CONF_MINIMUM_COMMAND_INTERVAL_MS: self.minimum_command_interval_ms,
            CONF_DIRECTION_CHANGE_DELAY_MS: self.direction_change_delay_ms,
            CONF_PULSE_INTERVAL_MS: self.pulse_interval_ms,
        }
        for field, value in non_negative.items():
            if value < 0:
                raise GateConfigError(field, "non_negative")

    def _validate_strategies(self) -> None:
        """Ensure each strategy can be executed by the configured topology."""
        if self.stop_strategy is StopStrategyType.CUSTOM_SEQUENCE:
            raise GateConfigError(CONF_STOP_STRATEGY, "custom_sequence_not_supported")
        if (
            self.direction_change_strategy
            is DirectionChangeStrategyType.CUSTOM_SEQUENCE
        ):
            raise GateConfigError(
                CONF_DIRECTION_CHANGE_STRATEGY,
                "custom_sequence_not_supported",
            )
        if RepeatedCommandPolicy.CUSTOM_SEQUENCE in (
            self.repeated_open_policy,
            self.repeated_close_policy,
        ):
            raise GateConfigError(
                CONF_REPEATED_OPEN_POLICY, "custom_sequence_not_supported"
            )
        if (
            self.stop_strategy is StopStrategyType.DEDICATED
            and self.stop_source is None
        ):
            raise GateConfigError(CONF_STOP_STRATEGY, "dedicated_stop_required")
        if self.stop_strategy in (
            StopStrategyType.HOLD_SAME_DIRECTION,
            StopStrategyType.HOLD_OPPOSITE_DIRECTION,
        ) and any(
            source.action_type is not ControlActionType.SWITCH
            for source in self._direction_sources()
        ):
            raise GateConfigError(CONF_STOP_STRATEGY, "hold_requires_switch")
        if (
            self.direction_change_strategy is DirectionChangeStrategyType.DIRECT
            and self.control_mode is ControlMode.SINGLE_STEP
        ):
            raise GateConfigError(
                CONF_DIRECTION_CHANGE_STRATEGY, "direct_requires_separate_controls"
            )
        if (
            self.direction_change_strategy
            in (
                DirectionChangeStrategyType.STOP_THEN_REVERSE,
                DirectionChangeStrategyType.STOP_WAIT_REVERSE,
            )
            and self.stop_strategy is StopStrategyType.UNSUPPORTED
        ):
            raise GateConfigError(
                CONF_DIRECTION_CHANGE_STRATEGY, "reversal_requires_stop"
            )
        if (
            self.direction_change_strategy is DirectionChangeStrategyType.MULTI_PULSE
            and self.pulse_count < 2
        ):
            raise GateConfigError(CONF_PULSE_COUNT, "multi_pulse_requires_multiple")
        if (
            RepeatedCommandPolicy.STOP
            in (
                self.repeated_open_policy,
                self.repeated_close_policy,
            )
            and self.stop_strategy is StopStrategyType.UNSUPPORTED
        ):
            raise GateConfigError(
                CONF_REPEATED_OPEN_POLICY, "repeated_stop_requires_stop"
            )

    def _direction_sources(self) -> tuple[SourceRef, ...]:
        """Return sources a same/opposite-direction strategy may need to hold."""
        if self.step_source is not None:
            return (self.step_source,)
        return tuple(
            source
            for source in (self.open_source, self.close_source)
            if source is not None
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the canonical JSON-safe ConfigEntry representation."""
        value: dict[str, Any] = {
            CONF_CONFIG_VERSION: self.config_version,
            CONF_DEVICE_ID: self.device_id,
            "name": self.name,
            CONF_CONTROL_MODE: self.control_mode.value,
            CONF_OPENING_TIME_MS: self.opening_time_ms,
            CONF_CLOSING_TIME_MS: self.closing_time_ms,
            CONF_OPENING_MARGIN_MS: self.opening_margin_ms,
            CONF_CLOSING_MARGIN_MS: self.closing_margin_ms,
            CONF_PULSE_DURATION_MS: self.pulse_duration_ms,
            CONF_HOLD_DURATION_MS: self.hold_duration_ms,
            CONF_MINIMUM_COMMAND_INTERVAL_MS: self.minimum_command_interval_ms,
            CONF_DIRECTION_CHANGE_DELAY_MS: self.direction_change_delay_ms,
            CONF_PULSE_INTERVAL_MS: self.pulse_interval_ms,
            CONF_PULSE_COUNT: self.pulse_count,
            CONF_STOP_STRATEGY: self.stop_strategy.value,
            CONF_DIRECTION_CHANGE_STRATEGY: self.direction_change_strategy.value,
            CONF_REPEATED_OPEN_POLICY: self.repeated_open_policy.value,
            CONF_REPEATED_CLOSE_POLICY: self.repeated_close_policy.value,
        }
        self._put_source(value, CONF_STEP_SOURCE, self.step_source)
        self._put_source(value, CONF_OPEN_SOURCE, self.open_source)
        self._put_source(value, CONF_CLOSE_SOURCE, self.close_source)
        self._put_source(value, CONF_STOP_SOURCE, self.stop_source)
        self._put_limit(value, CONF_OPEN_LIMIT, self.open_limit)
        self._put_limit(value, CONF_CLOSED_LIMIT, self.closed_limit)
        if self.obstacle_source is not None:
            value[CONF_OBSTACLE_SOURCE] = self.obstacle_source
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        """Restore and validate canonical ConfigEntry data."""
        return cls(
            config_version=int(value[CONF_CONFIG_VERSION]),
            device_id=str(value[CONF_DEVICE_ID]),
            name=str(value["name"]),
            control_mode=ControlMode(value[CONF_CONTROL_MODE]),
            step_source=cls._source_from(value, CONF_STEP_SOURCE),
            open_source=cls._source_from(value, CONF_OPEN_SOURCE),
            close_source=cls._source_from(value, CONF_CLOSE_SOURCE),
            stop_source=cls._source_from(value, CONF_STOP_SOURCE),
            open_limit=cls._limit_from(value, CONF_OPEN_LIMIT),
            closed_limit=cls._limit_from(value, CONF_CLOSED_LIMIT),
            obstacle_source=cls._optional_string(value, CONF_OBSTACLE_SOURCE),
            opening_time_ms=int(value[CONF_OPENING_TIME_MS]),
            closing_time_ms=int(value[CONF_CLOSING_TIME_MS]),
            opening_margin_ms=int(value[CONF_OPENING_MARGIN_MS]),
            closing_margin_ms=int(value[CONF_CLOSING_MARGIN_MS]),
            pulse_duration_ms=int(value[CONF_PULSE_DURATION_MS]),
            hold_duration_ms=int(value[CONF_HOLD_DURATION_MS]),
            minimum_command_interval_ms=int(value[CONF_MINIMUM_COMMAND_INTERVAL_MS]),
            direction_change_delay_ms=int(value[CONF_DIRECTION_CHANGE_DELAY_MS]),
            pulse_interval_ms=int(value[CONF_PULSE_INTERVAL_MS]),
            pulse_count=int(value[CONF_PULSE_COUNT]),
            stop_strategy=StopStrategyType(value[CONF_STOP_STRATEGY]),
            direction_change_strategy=DirectionChangeStrategyType(
                value[CONF_DIRECTION_CHANGE_STRATEGY]
            ),
            repeated_open_policy=RepeatedCommandPolicy(
                value[CONF_REPEATED_OPEN_POLICY]
            ),
            repeated_close_policy=RepeatedCommandPolicy(
                value[CONF_REPEATED_CLOSE_POLICY]
            ),
        )

    @staticmethod
    def _put_source(value: dict[str, Any], key: str, source: SourceRef | None) -> None:
        if source is not None:
            value[key] = source.to_dict()

    @staticmethod
    def _put_limit(
        value: dict[str, Any], key: str, limit: GateLimitConfig | None
    ) -> None:
        if limit is not None:
            value[key] = limit.to_dict()

    @staticmethod
    def _source_from(value: dict[str, Any], key: str) -> SourceRef | None:
        raw = value.get(key)
        return SourceRef.from_dict(raw) if isinstance(raw, dict) else None

    @staticmethod
    def _limit_from(value: dict[str, Any], key: str) -> GateLimitConfig | None:
        raw = value.get(key)
        return GateLimitConfig.from_dict(raw) if isinstance(raw, dict) else None

    @staticmethod
    def _optional_string(value: dict[str, Any], key: str) -> str | None:
        raw = value.get(key)
        return str(raw) if raw else None

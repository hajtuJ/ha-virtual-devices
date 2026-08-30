"""Native multi-step configuration flow for Virtual Devices."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.helpers import selector

from .const import (
    CONF_CLOSE_SOURCE,
    CONF_CLOSED_LIMIT,
    CONF_CLOSED_LIMIT_ACTIVE_STATE,
    CONF_CLOSED_LIMIT_DEBOUNCE_MS,
    CONF_CLOSING_MARGIN_MS,
    CONF_CLOSING_TIME_MS,
    CONF_CONTROL_MODE,
    CONF_DIRECTION_CHANGE_DELAY_MS,
    CONF_DIRECTION_CHANGE_STRATEGY,
    CONF_HOLD_DURATION_MS,
    CONF_MINIMUM_COMMAND_INTERVAL_MS,
    CONF_OBSTACLE_SOURCE,
    CONF_OPEN_LIMIT,
    CONF_OPEN_LIMIT_ACTIVE_STATE,
    CONF_OPEN_LIMIT_DEBOUNCE_MS,
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
    DOMAIN,
)
from .gate import (
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

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigFlowResult


DEFAULT_OPENING_TIME_MS = 15000
DEFAULT_CLOSING_TIME_MS = 15000
DEFAULT_MARGIN_MS = 2000
DEFAULT_DEBOUNCE_MS = 300
DEFAULT_PULSE_DURATION_MS = 500
DEFAULT_HOLD_DURATION_MS = 2200
DEFAULT_COMMAND_INTERVAL_MS = 700
DEFAULT_DIRECTION_CHANGE_DELAY_MS = 800
DEFAULT_PULSE_INTERVAL_MS = 700
DEFAULT_PULSE_COUNT = 2

CONTROL_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(
        filter=[{"domain": ["switch", "button"]}],
        multiple=False,
    )
)
BINARY_SENSOR_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(
        filter=[{"domain": "binary_sensor"}],
        multiple=False,
    )
)


def _number_selector(*, minimum: int, maximum: int) -> selector.NumberSelector:
    """Create a millisecond/integer selector with safe UI bounds."""
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=1,
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _select(values: list[str], translation_key: str) -> selector.SelectSelector:
    """Create a translated native single-choice selector."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=values,
            mode=selector.SelectSelectorMode.DROPDOWN,
            translation_key=translation_key,
        )
    )


class VirtualDevicesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure one independently managed virtual gate per config entry."""

    VERSION = 1
    MINOR_VERSION = 2

    _data: dict[str, Any]

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect gate identity and controller topology."""
        errors: dict[str, str] = {}
        if user_input is not None:
            name = str(user_input[CONF_NAME]).strip()
            if not name:
                errors[CONF_NAME] = "required"
            else:
                self._data = {
                    CONF_NAME: name,
                    CONF_CONTROL_MODE: user_input.get(
                        CONF_CONTROL_MODE, ControlMode.SINGLE_STEP.value
                    ),
                }
                return await self.async_step_controls()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): selector.TextSelector(),
                    vol.Required(
                        CONF_CONTROL_MODE,
                        default=ControlMode.SINGLE_STEP.value,
                    ): _select(
                        [mode.value for mode in ControlMode],
                        "control_mode",
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_controls(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the physical control sources required by the selected mode."""
        errors: dict[str, str] = {}
        if user_input is not None:
            entity_ids = [str(value) for value in user_input.values()]
            if len(entity_ids) != len(set(entity_ids)):
                errors["base"] = "duplicate_control_source"
            else:
                self._data.update(user_input)
                return await self.async_step_limits()

        return self.async_show_form(
            step_id="controls",
            data_schema=self._controls_schema(),
            errors=errors,
        )

    async def async_step_limits(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect optional endpoint and obstacle sensors."""
        errors: dict[str, str] = {}
        if user_input is not None:
            normalized = dict(user_input)
            for optional_entity in (
                CONF_OPEN_LIMIT,
                CONF_CLOSED_LIMIT,
                CONF_OBSTACLE_SOURCE,
            ):
                if not normalized.get(optional_entity):
                    normalized.pop(optional_entity, None)
            sensor_ids = [
                str(normalized[key])
                for key in (CONF_OPEN_LIMIT, CONF_CLOSED_LIMIT, CONF_OBSTACLE_SOURCE)
                if key in normalized
            ]
            if len(sensor_ids) != len(set(sensor_ids)):
                errors["base"] = "duplicate_sensor"
            else:
                self._data.update(normalized)
                return await self.async_step_timing()

        return self.async_show_form(
            step_id="limits",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_OPEN_LIMIT): BINARY_SENSOR_SELECTOR,
                    vol.Required(
                        CONF_OPEN_LIMIT_ACTIVE_STATE, default=True
                    ): selector.BooleanSelector(),
                    vol.Required(
                        CONF_OPEN_LIMIT_DEBOUNCE_MS,
                        default=DEFAULT_DEBOUNCE_MS,
                    ): _number_selector(minimum=0, maximum=60000),
                    vol.Optional(CONF_CLOSED_LIMIT): BINARY_SENSOR_SELECTOR,
                    vol.Required(
                        CONF_CLOSED_LIMIT_ACTIVE_STATE, default=True
                    ): selector.BooleanSelector(),
                    vol.Required(
                        CONF_CLOSED_LIMIT_DEBOUNCE_MS,
                        default=DEFAULT_DEBOUNCE_MS,
                    ): _number_selector(minimum=0, maximum=60000),
                    vol.Optional(CONF_OBSTACLE_SOURCE): BINARY_SENSOR_SELECTOR,
                }
            ),
            errors=errors,
        )

    async def async_step_timing(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect independent opening/closing travel and timeout margins."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_advanced()

        return self.async_show_form(
            step_id="timing",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_OPENING_TIME_MS, default=DEFAULT_OPENING_TIME_MS
                    ): _number_selector(minimum=1, maximum=3600000),
                    vol.Required(
                        CONF_CLOSING_TIME_MS, default=DEFAULT_CLOSING_TIME_MS
                    ): _number_selector(minimum=1, maximum=3600000),
                    vol.Required(
                        CONF_OPENING_MARGIN_MS, default=DEFAULT_MARGIN_MS
                    ): _number_selector(minimum=0, maximum=600000),
                    vol.Required(
                        CONF_CLOSING_MARGIN_MS, default=DEFAULT_MARGIN_MS
                    ): _number_selector(minimum=0, maximum=600000),
                }
            ),
        )

    async def async_step_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect command strategies and finish validated entry creation."""
        errors: dict[str, str] = {}
        if user_input is not None:
            candidate = {**self._data, **user_input}
            try:
                config = self._build_config(candidate)
            except GateConfigError as err:
                errors["base"] = err.code
            else:
                if self._is_duplicate(config):
                    return self.async_abort(reason="duplicate_gate")
                else:
                    await self.async_set_unique_id(config.device_id)
                    return self.async_create_entry(
                        title=config.name,
                        data=config.to_dict(),
                    )

        return self.async_show_form(
            step_id="advanced",
            data_schema=self._advanced_schema(),
            errors=errors,
        )

    def _controls_schema(self) -> vol.Schema:
        """Return a topology-specific source selection schema."""
        mode = ControlMode(self._data[CONF_CONTROL_MODE])
        if mode is ControlMode.SINGLE_STEP:
            fields: dict[vol.Marker, Any] = {
                vol.Required(CONF_STEP_SOURCE): CONTROL_SELECTOR
            }
        else:
            fields = {
                vol.Required(CONF_OPEN_SOURCE): CONTROL_SELECTOR,
                vol.Required(CONF_CLOSE_SOURCE): CONTROL_SELECTOR,
            }
            if mode is ControlMode.SEPARATE_OPEN_CLOSE_STOP:
                fields[vol.Required(CONF_STOP_SOURCE)] = CONTROL_SELECTOR
        return vol.Schema(fields)

    @staticmethod
    def _advanced_schema() -> vol.Schema:
        """Return the safe strategy subset supported by the MVP UI."""
        stop_strategies = [
            strategy.value
            for strategy in StopStrategyType
            if strategy is not StopStrategyType.CUSTOM_SEQUENCE
        ]
        direction_strategies = [
            strategy.value
            for strategy in DirectionChangeStrategyType
            if strategy is not DirectionChangeStrategyType.CUSTOM_SEQUENCE
        ]
        repeated_policies = [
            policy.value
            for policy in RepeatedCommandPolicy
            if policy is not RepeatedCommandPolicy.CUSTOM_SEQUENCE
        ]
        return vol.Schema(
            {
                vol.Required(
                    CONF_PULSE_DURATION_MS, default=DEFAULT_PULSE_DURATION_MS
                ): _number_selector(minimum=1, maximum=60000),
                vol.Required(
                    CONF_HOLD_DURATION_MS, default=DEFAULT_HOLD_DURATION_MS
                ): _number_selector(minimum=1, maximum=600000),
                vol.Required(
                    CONF_MINIMUM_COMMAND_INTERVAL_MS,
                    default=DEFAULT_COMMAND_INTERVAL_MS,
                ): _number_selector(minimum=0, maximum=600000),
                vol.Required(
                    CONF_DIRECTION_CHANGE_DELAY_MS,
                    default=DEFAULT_DIRECTION_CHANGE_DELAY_MS,
                ): _number_selector(minimum=0, maximum=600000),
                vol.Required(
                    CONF_PULSE_INTERVAL_MS,
                    default=DEFAULT_PULSE_INTERVAL_MS,
                ): _number_selector(minimum=0, maximum=600000),
                vol.Required(
                    CONF_PULSE_COUNT, default=DEFAULT_PULSE_COUNT
                ): _number_selector(minimum=1, maximum=20),
                vol.Required(
                    CONF_STOP_STRATEGY,
                    default=StopStrategyType.UNSUPPORTED.value,
                ): _select(stop_strategies, "stop_strategy"),
                vol.Required(
                    CONF_DIRECTION_CHANGE_STRATEGY,
                    default=DirectionChangeStrategyType.UNSUPPORTED.value,
                ): _select(direction_strategies, "direction_change_strategy"),
                vol.Required(
                    CONF_REPEATED_OPEN_POLICY,
                    default=RepeatedCommandPolicy.IGNORE.value,
                ): _select(repeated_policies, "repeated_command_policy"),
                vol.Required(
                    CONF_REPEATED_CLOSE_POLICY,
                    default=RepeatedCommandPolicy.IGNORE.value,
                ): _select(repeated_policies, "repeated_command_policy"),
            }
        )

    @staticmethod
    def _source(value: Any) -> SourceRef:
        """Convert a selector entity ID into the validated source abstraction."""
        entity_id = str(value)
        action_type = ControlActionType(entity_id.split(".", maxsplit=1)[0])
        return SourceRef(entity_id, action_type)

    @classmethod
    def _optional_source(cls, data: dict[str, Any], key: str) -> SourceRef | None:
        """Convert an optional source selector value."""
        return cls._source(data[key]) if key in data else None

    @staticmethod
    def _limit(
        data: dict[str, Any],
        entity_key: str,
        active_key: str,
        debounce_key: str,
    ) -> GateLimitConfig | None:
        """Build an optional endpoint configuration from one flow section."""
        if entity_key not in data:
            return None
        return GateLimitConfig(
            entity_id=str(data[entity_key]),
            active_state=bool(data[active_key]),
            debounce_ms=int(data[debounce_key]),
        )

    @classmethod
    def _build_config(cls, data: dict[str, Any]) -> GateConfig:
        """Build and comprehensively validate the canonical configuration."""
        return GateConfig(
            device_id=uuid4().hex,
            name=str(data[CONF_NAME]),
            control_mode=ControlMode(data[CONF_CONTROL_MODE]),
            step_source=cls._optional_source(data, CONF_STEP_SOURCE),
            open_source=cls._optional_source(data, CONF_OPEN_SOURCE),
            close_source=cls._optional_source(data, CONF_CLOSE_SOURCE),
            stop_source=cls._optional_source(data, CONF_STOP_SOURCE),
            open_limit=cls._limit(
                data,
                CONF_OPEN_LIMIT,
                CONF_OPEN_LIMIT_ACTIVE_STATE,
                CONF_OPEN_LIMIT_DEBOUNCE_MS,
            ),
            closed_limit=cls._limit(
                data,
                CONF_CLOSED_LIMIT,
                CONF_CLOSED_LIMIT_ACTIVE_STATE,
                CONF_CLOSED_LIMIT_DEBOUNCE_MS,
            ),
            obstacle_source=str(data[CONF_OBSTACLE_SOURCE])
            if CONF_OBSTACLE_SOURCE in data
            else None,
            opening_time_ms=int(data[CONF_OPENING_TIME_MS]),
            closing_time_ms=int(data[CONF_CLOSING_TIME_MS]),
            opening_margin_ms=int(data[CONF_OPENING_MARGIN_MS]),
            closing_margin_ms=int(data[CONF_CLOSING_MARGIN_MS]),
            pulse_duration_ms=int(data[CONF_PULSE_DURATION_MS]),
            hold_duration_ms=int(data[CONF_HOLD_DURATION_MS]),
            minimum_command_interval_ms=int(data[CONF_MINIMUM_COMMAND_INTERVAL_MS]),
            direction_change_delay_ms=int(data[CONF_DIRECTION_CHANGE_DELAY_MS]),
            pulse_interval_ms=int(data[CONF_PULSE_INTERVAL_MS]),
            pulse_count=int(data[CONF_PULSE_COUNT]),
            stop_strategy=StopStrategyType(data[CONF_STOP_STRATEGY]),
            direction_change_strategy=DirectionChangeStrategyType(
                data[CONF_DIRECTION_CHANGE_STRATEGY]
            ),
            repeated_open_policy=RepeatedCommandPolicy(data[CONF_REPEATED_OPEN_POLICY]),
            repeated_close_policy=RepeatedCommandPolicy(
                data[CONF_REPEATED_CLOSE_POLICY]
            ),
        )

    def _is_duplicate(self, candidate: GateConfig) -> bool:
        """Reject an accidental second gate owning the same control sources."""
        for entry in self._async_current_entries():
            try:
                existing = GateConfig.from_dict(dict(entry.data))
            except GateConfigError, KeyError, TypeError, ValueError:
                continue
            if existing.source_signature == candidate.source_signature:
                return True
        return False

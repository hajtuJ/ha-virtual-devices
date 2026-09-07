"""Tests for the complete Virtual Devices config flow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from custom_components.virtual_devices import (
    VirtualDevicesRuntimeData,
    async_migrate_entry,
)
from custom_components.virtual_devices.const import (
    CONF_CLOSE_SOURCE,
    CONF_CLOSED_LIMIT,
    CONF_CLOSED_LIMIT_ACTIVE_STATE,
    CONF_CLOSED_LIMIT_DEBOUNCE_MS,
    CONF_CONTROL_MODE,
    CONF_DIRECTION_CHANGE_STRATEGY,
    CONF_HOLD_DURATION_MS,
    CONF_MINIMUM_COMMAND_INTERVAL_MS,
    CONF_OPEN_LIMIT,
    CONF_OPEN_LIMIT_ACTIVE_STATE,
    CONF_OPEN_LIMIT_DEBOUNCE_MS,
    CONF_OPEN_SOURCE,
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
from custom_components.virtual_devices.gate import (
    ControlActionType,
    ControlMode,
    DirectionChangeStrategyType,
    GateConfig,
    SourceRef,
    StopStrategyType,
)
from homeassistant import config_entries
from homeassistant.const import CONF_NAME, STATE_OFF, STATE_ON
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector
from pytest_homeassistant_custom_component.common import (  # type: ignore[import-untyped]
    MockConfigEntry,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigFlowResult
    from homeassistant.core import HomeAssistant, ServiceCall


async def advance_to_advanced(
    hass: HomeAssistant,
    *,
    name: str = "Driveway Gate",
    mode: ControlMode = ControlMode.SINGLE_STEP,
    controls: dict[str, str] | None = None,
    limits: dict[str, Any] | None = None,
) -> ConfigFlowResult:
    """Advance a flow through every basic native-UI step."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: name, CONF_CONTROL_MODE: mode.value},
    )
    assert result["step_id"] == "controls"

    if controls is None:
        controls = {CONF_STEP_SOURCE: "switch.gate"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], controls)
    assert result["step_id"] == "limits"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], limits or {}
    )
    assert result["step_id"] == "timing"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "advanced"
    return result


async def create_gate(
    hass: HomeAssistant,
    **kwargs: Any,
) -> ConfigFlowResult:
    """Complete a valid flow using safe advanced defaults."""
    result = await advance_to_advanced(hass, **kwargs)
    return await hass.config_entries.flow.async_configure(result["flow_id"], {})


async def test_full_flow_creates_loads_and_unloads_typed_entry(
    hass: HomeAssistant,
) -> None:
    """A five-step flow stores canonical data and loads without physical actions."""
    service_calls: list[ServiceCall] = []

    async def record_call(call: ServiceCall) -> None:
        service_calls.append(call)

    hass.services.async_register("switch", "turn_on", record_call)
    hass.services.async_register("switch", "turn_off", record_call)
    hass.services.async_register("button", "press", record_call)

    result = await create_gate(
        hass,
        mode=ControlMode.SEPARATE_OPEN_CLOSE_STOP,
        controls={
            CONF_OPEN_SOURCE: "switch.gate_open",
            CONF_CLOSE_SOURCE: "switch.gate_close",
            CONF_STOP_SOURCE: "button.gate_stop",
        },
        limits={
            CONF_OPEN_LIMIT: "binary_sensor.gate_open",
            CONF_OPEN_LIMIT_ACTIVE_STATE: STATE_OFF,
            CONF_OPEN_LIMIT_DEBOUNCE_MS: 0,
            CONF_CLOSED_LIMIT: "binary_sensor.gate_closed",
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Driveway Gate"
    config = GateConfig.from_dict(dict(result["data"]))
    assert config.control_mode is ControlMode.SEPARATE_OPEN_CLOSE_STOP
    assert config.open_limit is not None
    assert not config.open_limit.active_state
    assert config.open_limit.debounce_ms == 0
    assert config.closed_limit is not None
    assert len(config.device_id) == 32

    entry = result["result"]
    assert entry.state.value == config_entries.ConfigEntryState.LOADED.value
    assert isinstance(entry.runtime_data, VirtualDevicesRuntimeData)
    assert entry.runtime_data.config == config
    assert service_calls == []

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state.value == config_entries.ConfigEntryState.NOT_LOADED.value
    assert service_calls == []


async def test_limit_form_explicitly_selects_reached_state(
    hass: HomeAssistant,
) -> None:
    """Each endpoint declares whether ON or OFF means physically reached."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={
            CONF_NAME: "Explicit limit states",
            CONF_CONTROL_MODE: ControlMode.ASYMMETRIC_SINGLE_STEP.value,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_STEP_SOURCE: "button.explicit_limit_gate"}
    )

    assert result["step_id"] == "limits"
    schema = result["data_schema"]
    assert schema is not None
    for active_key in (
        CONF_OPEN_LIMIT_ACTIVE_STATE,
        CONF_CLOSED_LIMIT_ACTIVE_STATE,
    ):
        active_selector = next(
            field
            for marker, field in schema.schema.items()
            if marker.schema == active_key
        )
        assert isinstance(active_selector, selector.SelectSelector)
        assert active_selector.config["options"] == [STATE_ON, STATE_OFF]
        assert active_selector.config["translation_key"] == "limit_active_state"

    defaults = schema({CONF_CLOSED_LIMIT: "binary_sensor.explicit_closed"})
    assert defaults[CONF_OPEN_LIMIT_ACTIVE_STATE] == STATE_ON
    assert defaults[CONF_CLOSED_LIMIT_ACTIVE_STATE] == STATE_ON

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_CLOSED_LIMIT: "binary_sensor.explicit_closed",
            CONF_CLOSED_LIMIT_ACTIVE_STATE: STATE_OFF,
            CONF_CLOSED_LIMIT_DEBOUNCE_MS: 0,
            CONF_OPEN_LIMIT: "binary_sensor.explicit_open",
            CONF_OPEN_LIMIT_ACTIVE_STATE: STATE_ON,
            CONF_OPEN_LIMIT_DEBOUNCE_MS: 0,
        },
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    config = GateConfig.from_dict(dict(result["data"]))
    assert config.closed_limit is not None
    assert not config.closed_limit.active_state
    assert config.open_limit is not None
    assert config.open_limit.active_state


async def test_two_distinct_gates_have_independent_stable_identity(
    hass: HomeAssistant,
) -> None:
    """Two different source sets create independent entries and UUID identities."""
    first = await create_gate(
        hass,
        name="Driveway Gate",
        controls={CONF_STEP_SOURCE: "button.driveway_gate"},
    )
    second = await create_gate(
        hass,
        name="Garden Gate",
        controls={CONF_STEP_SOURCE: "button.garden_gate"},
    )

    assert first["type"] is FlowResultType.CREATE_ENTRY
    assert second["type"] is FlowResultType.CREATE_ENTRY
    assert first["result"].unique_id != second["result"].unique_id
    assert first["data"]["device_id"] != second["data"]["device_id"]


async def test_duplicate_control_selection_is_rejected(
    hass: HomeAssistant,
) -> None:
    """OPEN and CLOSE cannot own the same physical control."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={
            CONF_NAME: "Unsafe Gate",
            CONF_CONTROL_MODE: ControlMode.SEPARATE_OPEN_CLOSE.value,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_OPEN_SOURCE: "switch.gate",
            CONF_CLOSE_SOURCE: "switch.gate",
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "controls"
    assert result["errors"] == {"base": "duplicate_control_source"}


async def test_duplicate_sensor_roles_are_rejected(hass: HomeAssistant) -> None:
    """One binary sensor cannot simultaneously represent both endpoints."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={
            CONF_NAME: "Unsafe Gate",
            CONF_CONTROL_MODE: ControlMode.SINGLE_STEP.value,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_STEP_SOURCE: "button.gate"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_OPEN_LIMIT: "binary_sensor.gate_limit",
            CONF_CLOSED_LIMIT: "binary_sensor.gate_limit",
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "limits"
    assert result["errors"] == {"base": "duplicate_sensor"}


async def test_incompatible_strategy_returns_translated_error(
    hass: HomeAssistant,
) -> None:
    """Direct reversal is impossible for a single step-by-step source."""
    result = await advance_to_advanced(hass, controls={CONF_STEP_SOURCE: "button.gate"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_DIRECTION_CHANGE_STRATEGY: DirectionChangeStrategyType.DIRECT.value},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "advanced"
    assert result["errors"] == {"base": "direct_requires_separate_controls"}


async def test_dedicated_stop_strategy_requires_stop_source(
    hass: HomeAssistant,
) -> None:
    """The strategy is rejected when the selected mode has no STOP control."""
    result = await advance_to_advanced(
        hass,
        mode=ControlMode.SEPARATE_OPEN_CLOSE,
        controls={
            CONF_OPEN_SOURCE: "button.gate_open",
            CONF_CLOSE_SOURCE: "button.gate_close",
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_STOP_STRATEGY: StopStrategyType.DEDICATED.value},
    )
    assert result["errors"] == {"base": "dedicated_stop_required"}


async def test_asymmetric_flow_requires_closed_limit_and_hides_generic_strategies(
    hass: HomeAssistant,
) -> None:
    """The dedicated profile exposes only timings that cannot change its cycle."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={
            CONF_NAME: "Asymmetric Gate",
            CONF_CONTROL_MODE: ControlMode.ASYMMETRIC_SINGLE_STEP.value,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_STEP_SOURCE: "button.gate"}
    )
    assert result["step_id"] == "limits"
    assert result["data_schema"] is not None
    assert any(
        isinstance(key, vol.Required) and key.schema == CONF_CLOSED_LIMIT
        for key in result["data_schema"].schema
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_CLOSED_LIMIT: "binary_sensor.gate_closed",
            CONF_CLOSED_LIMIT_DEBOUNCE_MS: 0,
        },
    )
    assert result["step_id"] == "timing"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "advanced"
    assert result["data_schema"] is not None

    schema_keys = {str(key.schema) for key in result["data_schema"].schema}
    assert schema_keys == {
        CONF_PULSE_DURATION_MS,
        CONF_MINIMUM_COMMAND_INTERVAL_MS,
        CONF_PULSE_INTERVAL_MS,
    }
    assert CONF_HOLD_DURATION_MS not in schema_keys
    assert CONF_PULSE_COUNT not in schema_keys
    assert CONF_STOP_STRATEGY not in schema_keys
    assert CONF_DIRECTION_CHANGE_STRATEGY not in schema_keys
    assert CONF_REPEATED_OPEN_POLICY not in schema_keys
    assert CONF_REPEATED_CLOSE_POLICY not in schema_keys

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    config = GateConfig.from_dict(dict(result["data"]))
    assert config.control_mode is ControlMode.ASYMMETRIC_SINGLE_STEP
    assert config.closed_limit is not None
    assert config.open_limit is None
    assert config.pulse_count == 2
    assert config.stop_strategy is StopStrategyType.UNSUPPORTED
    assert config.direction_change_strategy is DirectionChangeStrategyType.UNSUPPORTED


async def test_asymmetric_flow_accepts_closed_and_open_limits(
    hass: HomeAssistant,
) -> None:
    """The same fixed profile supports authoritative sensors at both endpoints."""
    result = await advance_to_advanced(
        hass,
        name="Two-limit Asymmetric Gate",
        mode=ControlMode.ASYMMETRIC_SINGLE_STEP,
        controls={CONF_STEP_SOURCE: "button.two_limit_gate"},
        limits={
            CONF_CLOSED_LIMIT: "binary_sensor.two_limit_closed",
            CONF_CLOSED_LIMIT_DEBOUNCE_MS: 0,
            CONF_OPEN_LIMIT: "binary_sensor.two_limit_open",
            CONF_OPEN_LIMIT_DEBOUNCE_MS: 0,
        },
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    config = GateConfig.from_dict(dict(result["data"]))
    assert config.control_mode is ControlMode.ASYMMETRIC_SINGLE_STEP
    assert config.closed_limit is not None
    assert config.open_limit is not None


async def test_duplicate_gate_aborts_without_creating_another_entry(
    hass: HomeAssistant,
) -> None:
    """An identical source ownership signature is rejected as a duplicate."""
    first = await create_gate(hass)
    assert first["type"] is FlowResultType.CREATE_ENTRY

    duplicate = await create_gate(hass, name="Same Hardware")
    assert duplicate["type"] is FlowResultType.ABORT
    assert duplicate["reason"] == "duplicate_gate"


async def test_reconfigure_preserves_identity_reloads_and_replaces_listeners(
    hass: HomeAssistant,
) -> None:
    """Required setup can change without movement or duplicate registries."""
    service_calls: list[ServiceCall] = []

    async def record(call: ServiceCall) -> None:
        service_calls.append(call)

    hass.services.async_register("button", "press", record)
    hass.states.async_set("button.old_gate", "off")
    hass.states.async_set("button.new_gate", "off")
    hass.states.async_set("binary_sensor.old_closed", "on")
    hass.states.async_set("binary_sensor.new_closed", "on")
    created = await create_gate(
        hass,
        controls={CONF_STEP_SOURCE: "button.old_gate"},
        limits={
            CONF_CLOSED_LIMIT: "binary_sensor.old_closed",
            CONF_CLOSED_LIMIT_ACTIVE_STATE: STATE_OFF,
            CONF_CLOSED_LIMIT_DEBOUNCE_MS: 0,
        },
    )
    entry = created["result"]
    original = GateConfig.from_dict(dict(entry.data))
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    cover_entry = entity_registry.async_get("cover.driveway_gate")
    device = device_registry.async_get_device(
        identifiers={(DOMAIN, original.device_id)}
    )
    assert cover_entry is not None
    assert device is not None
    original_entity_unique_id = cover_entry.unique_id
    original_device_registry_id = device.id

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Renamed Gate",
            CONF_CONTROL_MODE: ControlMode.SINGLE_STEP.value,
        },
    )
    assert result["step_id"] == "controls"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_STEP_SOURCE: "button.new_gate"}
    )
    assert result["step_id"] == "limits"
    limits_schema = result["data_schema"]
    assert limits_schema is not None
    limits_defaults = limits_schema(
        {
            CONF_CLOSED_LIMIT: "binary_sensor.new_closed",
            CONF_CLOSED_LIMIT_DEBOUNCE_MS: 0,
        }
    )
    assert limits_defaults[CONF_CLOSED_LIMIT_ACTIVE_STATE] == STATE_OFF
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_CLOSED_LIMIT: "binary_sensor.new_closed",
            CONF_CLOSED_LIMIT_DEBOUNCE_MS: 0,
        },
    )
    assert result["step_id"] == "timing"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "advanced"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()

    updated = GateConfig.from_dict(dict(entry.data))
    assert updated.device_id == original.device_id
    assert updated.closed_limit is not None
    assert not updated.closed_limit.active_state
    assert entry.unique_id == original.device_id
    assert entry.title == "Renamed Gate"
    updated_cover = entity_registry.async_get("cover.driveway_gate")
    updated_device = device_registry.async_get_device(
        identifiers={(DOMAIN, original.device_id)}
    )
    assert updated_cover is not None
    assert updated_cover.unique_id == original_entity_unique_id
    assert updated_device is not None
    assert updated_device.id == original_device_registry_id
    assert service_calls == []

    controller = entry.runtime_data.controller
    hass.states.async_set("binary_sensor.old_closed", "off")
    await hass.async_block_till_done()
    assert controller.snapshot.state.value == "unknown"
    hass.states.async_set("binary_sensor.new_closed", "off")
    await hass.async_block_till_done()
    assert controller.snapshot.state.value == "closed"


async def test_minor_version_migration_normalizes_without_movement(
    hass: HomeAssistant,
) -> None:
    """Stored schema migration changes data only and never calls a source."""
    calls: list[ServiceCall] = []

    async def record(call: ServiceCall) -> None:
        calls.append(call)

    hass.services.async_register("button", "press", record)
    config = GateConfig(
        device_id="migration-id",
        name="Migration Gate",
        control_mode=ControlMode.SINGLE_STEP,
        step_source=SourceRef("button.migration_gate", ControlActionType.BUTTON),
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=config.name,
        unique_id=config.device_id,
        data=config.to_dict(),
        version=1,
        minor_version=1,
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry)
    assert entry.version == 1
    assert entry.minor_version == 2
    assert GateConfig.from_dict(dict(entry.data)) == config
    assert calls == []

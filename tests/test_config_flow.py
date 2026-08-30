"""Tests for the complete Virtual Devices config flow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from custom_components.virtual_devices import VirtualDevicesRuntimeData
from custom_components.virtual_devices.const import (
    CONF_CLOSE_SOURCE,
    CONF_CLOSED_LIMIT,
    CONF_CONTROL_MODE,
    CONF_DIRECTION_CHANGE_STRATEGY,
    CONF_OPEN_LIMIT,
    CONF_OPEN_LIMIT_ACTIVE_STATE,
    CONF_OPEN_LIMIT_DEBOUNCE_MS,
    CONF_OPEN_SOURCE,
    CONF_STEP_SOURCE,
    CONF_STOP_SOURCE,
    CONF_STOP_STRATEGY,
    DOMAIN,
)
from custom_components.virtual_devices.gate import (
    ControlMode,
    DirectionChangeStrategyType,
    GateConfig,
    StopStrategyType,
)
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.data_entry_flow import FlowResultType

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
            CONF_OPEN_LIMIT_ACTIVE_STATE: False,
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


async def test_duplicate_gate_aborts_without_creating_another_entry(
    hass: HomeAssistant,
) -> None:
    """An identical source ownership signature is rejected as a duplicate."""
    first = await create_gate(hass)
    assert first["type"] is FlowResultType.CREATE_ENTRY

    duplicate = await create_gate(hass, name="Same Hardware")
    assert duplicate["type"] is FlowResultType.ABORT
    assert duplicate["reason"] == "duplicate_gate"

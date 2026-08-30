"""Tests for the Virtual Devices config flow."""

from typing import TYPE_CHECKING

from custom_components.virtual_devices import VirtualDevicesRuntimeData
from custom_components.virtual_devices.const import CONF_DEVICE_ID, DOMAIN
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.data_entry_flow import FlowResultType

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


async def test_user_flow_creates_and_loads_entry(hass: HomeAssistant) -> None:
    """Test creating one virtual gate without physical side effects."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Driveway Gate"},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Driveway Gate"
    assert result["data"][CONF_NAME] == "Driveway Gate"
    assert len(result["data"][CONF_DEVICE_ID]) == 32

    entry = result["result"]
    assert entry.state is config_entries.ConfigEntryState.LOADED
    assert entry.runtime_data == VirtualDevicesRuntimeData(
        device_id=result["data"][CONF_DEVICE_ID],
        name="Driveway Gate",
    )


async def test_multiple_gates_have_distinct_identity(hass: HomeAssistant) -> None:
    """Test that multiple virtual gates can coexist."""
    entries = []

    for name in ("Driveway Gate", "Garden Gate"):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={CONF_NAME: name},
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        entries.append(result["result"])

    assert entries[0].unique_id != entries[1].unique_id
    assert entries[0].data[CONF_DEVICE_ID] != entries[1].data[CONF_DEVICE_ID]


async def test_entry_unloads_cleanly(hass: HomeAssistant) -> None:
    """Test unloading the side-effect-free integration scaffold."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={CONF_NAME: "Driveway Gate"},
    )
    entry = result["result"]

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is config_entries.ConfigEntryState.NOT_LOADED

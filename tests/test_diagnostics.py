"""Tests for redacted Virtual Devices diagnostics."""

from typing import TYPE_CHECKING

from custom_components.virtual_devices.const import DOMAIN
from custom_components.virtual_devices.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.virtual_devices.gate import (
    ControlActionType,
    ControlMode,
    GateConfig,
    SourceRef,
)
from pytest_homeassistant_custom_component.common import (  # type: ignore[import-untyped]
    MockConfigEntry,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


async def setup_gate(hass: HomeAssistant, config: GateConfig) -> MockConfigEntry:
    """Set up one diagnostic test entry."""
    for source in config.control_sources:
        hass.states.async_set(source.entity_id, "off")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=config.name,
        unique_id=config.device_id,
        data=config.to_dict(),
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_diagnostics_are_useful_and_redact_names_and_entity_ids(
    hass: HomeAssistant,
) -> None:
    config = GateConfig(
        device_id="diagnostic-id",
        name="Private Driveway",
        control_mode=ControlMode.SINGLE_STEP,
        step_source=SourceRef("button.private_driveway", ControlActionType.BUTTON),
        minimum_command_interval_ms=0,
    )
    entry = await setup_gate(hass, config)
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    rendered = str(diagnostics)

    assert diagnostics["config"]["control_mode"] == "single_step"
    assert diagnostics["config"]["control_source_count"] == 1
    assert diagnostics["runtime"]["state"] == "unknown"
    assert "Private Driveway" not in rendered
    assert "button.private_driveway" not in rendered
    assert "diagnostic-id" not in rendered

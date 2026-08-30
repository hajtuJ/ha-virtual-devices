"""The Virtual Devices integration."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry

from .gate import GateConfig, GateController
from .gate.ha_source_actions import HomeAssistantSourceActions

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


@dataclass(frozen=True, slots=True)
class VirtualDevicesRuntimeData:
    """Runtime data for one configured virtual device."""

    config: GateConfig
    controller: GateController

    @property
    def device_id(self) -> str:
        """Return the stable device identifier."""
        return self.config.device_id

    @property
    def name(self) -> str:
        """Return the configured gate name."""
        return self.config.name


type VirtualDevicesConfigEntry = ConfigEntry[VirtualDevicesRuntimeData]


async def async_setup_entry(
    hass: HomeAssistant, entry: VirtualDevicesConfigEntry
) -> bool:
    """Set up Virtual Devices from a config entry without physical side effects."""
    config = GateConfig.from_dict(dict(entry.data))
    entry.runtime_data = VirtualDevicesRuntimeData(
        config=config,
        controller=GateController(config, HomeAssistantSourceActions(hass)),
    )
    await entry.runtime_data.controller.async_initialize()
    await hass.config_entries.async_forward_entry_setups(entry, ["cover"])
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: VirtualDevicesConfigEntry
) -> bool:
    """Unload a Virtual Devices config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["cover"])
    if unload_ok:
        await entry.runtime_data.controller.async_shutdown()
    return unload_ok

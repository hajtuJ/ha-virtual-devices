"""The Virtual Devices integration."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry

from .gate import GateConfig

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


@dataclass(frozen=True, slots=True)
class VirtualDevicesRuntimeData:
    """Runtime data for one configured virtual device."""

    config: GateConfig

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
    entry.runtime_data = VirtualDevicesRuntimeData(
        config=GateConfig.from_dict(dict(entry.data))
    )
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: VirtualDevicesConfigEntry
) -> bool:
    """Unload a Virtual Devices config entry."""
    return True

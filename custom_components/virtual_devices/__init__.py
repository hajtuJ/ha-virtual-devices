"""The Virtual Devices integration."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME

from .const import CONF_DEVICE_ID

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


@dataclass(frozen=True, slots=True)
class VirtualDevicesRuntimeData:
    """Runtime data for one configured virtual device."""

    device_id: str
    name: str


type VirtualDevicesConfigEntry = ConfigEntry[VirtualDevicesRuntimeData]


async def async_setup_entry(
    hass: HomeAssistant, entry: VirtualDevicesConfigEntry
) -> bool:
    """Set up Virtual Devices from a config entry without physical side effects."""
    entry.runtime_data = VirtualDevicesRuntimeData(
        device_id=entry.data[CONF_DEVICE_ID],
        name=entry.data[CONF_NAME],
    )
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: VirtualDevicesConfigEntry
) -> bool:
    """Unload a Virtual Devices config entry."""
    return True

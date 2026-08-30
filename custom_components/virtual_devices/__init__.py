"""The Virtual Devices integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry

from .const import PLATFORMS
from .gate import GateConfig, GateController
from .gate.ha_source_actions import HomeAssistantSourceActions
from .gate.observer import GateSourceObserver
from .gate.persistence import GatePersistence

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant


@dataclass(frozen=True, slots=True)
class VirtualDevicesRuntimeData:
    """Runtime data for one configured virtual device."""

    config: GateConfig
    controller: GateController
    observer: GateSourceObserver
    persistence: GatePersistence
    remove_persistence_callback: Callable[[], None]

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
    persistence = GatePersistence(hass, entry.entry_id)
    restored = await persistence.async_load()
    controller = GateController(
        config,
        HomeAssistantSourceActions(hass),
        initial_snapshot=restored,
        hass=hass,
    )
    observer = GateSourceObserver(hass, config, controller)
    await observer.async_start()
    await controller.async_restore()
    remove_persistence_callback = controller.async_add_update_callback(
        lambda: persistence.schedule_save(controller.snapshot)
    )
    entry.runtime_data = VirtualDevicesRuntimeData(
        config=config,
        controller=controller,
        observer=observer,
        persistence=persistence,
        remove_persistence_callback=remove_persistence_callback,
    )
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        remove_persistence_callback()
        await observer.async_shutdown()
        await controller.async_shutdown()
        raise
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: VirtualDevicesConfigEntry
) -> bool:
    """Unload a Virtual Devices config entry."""
    runtime = entry.runtime_data
    await runtime.observer.async_shutdown()
    await runtime.controller.async_shutdown()
    runtime.remove_persistence_callback()
    await runtime.persistence.async_flush(runtime.controller.snapshot)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    return unload_ok

"""The re@di Open Data integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ReadiClient
from .const import DOMAIN
from .coordinator import ReadiConfigEntry, ReadiCoordinator, device_id

PLATFORMS = [Platform.SENSOR, Platform.WEATHER]


async def async_setup_entry(hass: HomeAssistant, entry: ReadiConfigEntry) -> bool:
    """Set up one city."""
    coordinator = ReadiCoordinator(hass, entry, ReadiClient(async_get_clientsession(hass)))
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # Remove devices of sensors the user deselected.
    selected = {(DOMAIN, device_id(s)) for s in coordinator.sensors}
    registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        if not device.identifiers & selected:
            registry.async_update_device(device.id, remove_config_entry_id=entry.entry_id)

    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_reload(hass: HomeAssistant, entry: ReadiConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ReadiConfigEntry) -> bool:
    """Unload a city."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

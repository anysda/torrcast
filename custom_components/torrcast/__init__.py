"""Sets up torrcast from a config entry: one serve, one coordinator, one player."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_loaded_integration

from .coordinator import TorrcastConfigEntry, TorrcastCoordinator

PLATFORMS: list[Platform] = [Platform.MEDIA_PLAYER]


async def async_setup_entry(hass: HomeAssistant, entry: TorrcastConfigEntry) -> bool:
    """Builds the coordinator, gets the first snapshot and hands it to the platform."""
    integration = async_get_loaded_integration(hass, entry.domain)
    version = None if integration.version is None else str(integration.version)
    coordinator = TorrcastCoordinator(
        hass,
        entry,
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        version,
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TorrcastConfigEntry) -> bool:
    """Takes the player down; the coordinator dies with the entry itself."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

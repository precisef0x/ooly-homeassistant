"""The OOLY integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import OolyClient
from .const import DOMAIN
from .coordinator import OolyCoordinator

PLATFORMS: list[Platform] = [Platform.LIGHT]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up OOLY from a config entry."""
    client = OolyClient(entry.data[CONF_HOST], async_get_clientsession(hass))
    coordinator = OolyCoordinator(hass, client, entry)
    await coordinator.async_config_entry_first_refresh()
    # Capture the device's real CCT range (used by the colour-temperature slider).
    await coordinator.async_load_cct_bounds()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    # The light now has a native colour-temperature slider; remove a Kelvin `number`
    # left by an earlier version so it doesn't linger as an orphan entity.
    registry = er.async_get(hass)
    device_id = entry.unique_id or entry.entry_id
    if eid := registry.async_get_entity_id("number", DOMAIN, f"{device_id}_cct_k"):
        registry.async_remove(eid)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok

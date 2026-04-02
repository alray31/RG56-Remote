"""RG56 Remote — Midea IR climate integration for Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

DOMAIN = "rg56_remote"
PLATFORMS = ["climate", "button", "switch"]

CONF_INFRARED_ENTITY_ID = "infrared_entity_id"
CONF_TEMPERATURE_SENSOR = "temperature_sensor"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up RG56 Remote from a config entry."""
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

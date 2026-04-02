"""Switch entity for Follow Me mode on RG56 Remote."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([FollowMeSwitch(entry)])


class FollowMeSwitch(SwitchEntity):
    """Switch to enable/disable Follow Me mode."""

    _attr_has_entity_name = True
    _attr_name = "Follow Me Mode"
    _attr_icon = "mdi:transit-connection-variant"

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_follow_me"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "RG56 Remote",
            "manufacturer": "Midea",
            "model": "RG56/BGEFU1-CA",
        }
        self._attr_is_on = False

    def _get_climate(self):
        """Get the climate entity from hass."""
        entity_id = f"climate.rg56_remote"
        # Look up by unique_id prefix
        from homeassistant.helpers import entity_registry as er
        ent_reg = er.async_get(self.hass)
        for entry in ent_reg.entities.values():
            if entry.unique_id == f"{self._entry.entry_id}_climate":
                entity_id = entry.entity_id
                break
        return self.hass.states.get(entity_id)

    async def async_turn_on(self, **kwargs) -> None:
        self._attr_is_on = True
        self.async_write_ha_state()
        # Find and call the climate entity
        await self._toggle_follow_me(True)

    async def async_turn_off(self, **kwargs) -> None:
        self._attr_is_on = False
        self.async_write_ha_state()
        await self._toggle_follow_me(False)

    async def _toggle_follow_me(self, enable: bool) -> None:
        from homeassistant.helpers import entity_registry as er
        ent_reg = er.async_get(self.hass)
        climate_entity_id = None
        for entry in ent_reg.entities.values():
            if entry.unique_id == f"{self._entry.entry_id}_climate":
                climate_entity_id = entry.entity_id
                break

        if climate_entity_id is None:
            return

        # Get the actual entity object from the platform
        component = self.hass.data.get("climate")
        if component is None:
            return

        entity = component.get_entity(climate_entity_id)
        if entity is None:
            return

        if enable:
            await entity.async_enable_follow_me()
        else:
            await entity.async_disable_follow_me()

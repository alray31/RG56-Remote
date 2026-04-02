"""Button entities for RG56 Remote special IR commands."""

from __future__ import annotations

from dataclasses import dataclass

from infrared_protocols import Command

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CONF_INFRARED_ENTITY_ID, DOMAIN
from .base import MideaIRMixin
from .midea import (
    DEFLECTORS_POSITION,
    DEFLECTORS_SWING,
    FRONT_PANEL_LIGHTS,
    SELF_CLEAN,
    TURBO,
)


@dataclass
class RG56ButtonDescription:
    key: str
    name: str
    icon: str
    command: Command


BUTTONS: list[RG56ButtonDescription] = [
    RG56ButtonDescription("front_panel_lights", "Front Panel Lights", "mdi:led-on", FRONT_PANEL_LIGHTS),
    RG56ButtonDescription("deflectors_position", "Deflectors Position", "mdi:arrow-up-down-bold", DEFLECTORS_POSITION),
    RG56ButtonDescription("self_clean", "Self Clean", "mdi:broom", SELF_CLEAN),
    RG56ButtonDescription("turbo", "Turbo", "mdi:car-turbocharger", TURBO),
    RG56ButtonDescription("deflectors_swing", "Deflectors Swing", "mdi:arrow-oscillating", DEFLECTORS_SWING),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    infrared_entity_id: str = entry.data[CONF_INFRARED_ENTITY_ID]
    async_add_entities([
        RG56Button(entry, desc, infrared_entity_id)
        for desc in BUTTONS
    ])


class RG56Button(MideaIRMixin, ButtonEntity):
    """A button that fires one RG56 IR command."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        desc: RG56ButtonDescription,
        infrared_entity_id: str,
    ) -> None:
        self._desc = desc
        self._infrared_entity_id = infrared_entity_id
        self._attr_name = desc.name
        self._attr_icon = desc.icon
        self._attr_unique_id = f"{entry.entry_id}_btn_{desc.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "RG56 Remote",
            "manufacturer": "Midea",
            "model": "RG56/BGEFU1-CA",
        }

    async def async_press(self) -> None:
        await self._send(self._desc.command)

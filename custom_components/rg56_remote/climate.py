"""Climate entity for RG56 Remote (Midea IR) with Follow Me mode."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.climate.const import FAN_AUTO, FAN_HIGH, FAN_LOW, FAN_MEDIUM
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.util import dt as dt_util

from . import CONF_INFRARED_ENTITY_ID, CONF_TEMPERATURE_SENSOR, DOMAIN
from .base import MideaIRMixin
from .midea import MideaClimateCommand, make_follow_me_command

_LOGGER = logging.getLogger(__name__)

FOLLOW_ME_INTERVAL = 180  # seconds

SUPPORTED_HVAC_MODES = [
    HVACMode.OFF,
    HVACMode.COOL,
    HVACMode.HEAT,
    HVACMode.DRY,
    HVACMode.FAN_ONLY,
    HVACMode.AUTO,
]

SUPPORTED_FAN_MODES = [FAN_AUTO, FAN_LOW, FAN_MEDIUM, FAN_HIGH]

SUPPORTED_FEATURES = (
    ClimateEntityFeature.TARGET_TEMPERATURE
    | ClimateEntityFeature.FAN_MODE
    | ClimateEntityFeature.TURN_ON
    | ClimateEntityFeature.TURN_OFF
)

_HVAC_TO_MIDEA = {
    HVACMode.COOL: "cool",
    HVACMode.HEAT: "heat",
    HVACMode.DRY: "dry",
    HVACMode.FAN_ONLY: "fan_only",
    HVACMode.AUTO: "auto",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([RG56ClimateEntity(entry)])


class RG56ClimateEntity(MideaIRMixin, ClimateEntity):
    """Midea IR climate entity with Follow Me support."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_hvac_modes = SUPPORTED_HVAC_MODES
    _attr_fan_modes = SUPPORTED_FAN_MODES
    _attr_supported_features = SUPPORTED_FEATURES
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 17
    _attr_max_temp = 30
    _attr_target_temperature_step = 1
    _attr_assumed_state = True

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._infrared_entity_id: str = entry.data[CONF_INFRARED_ENTITY_ID]
        self._temperature_sensor: str = entry.data[CONF_TEMPERATURE_SENSOR]
        self._attr_unique_id = f"{entry.entry_id}_climate"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "RG56 Remote",
            "manufacturer": "Midea",
            "model": "RG56/BGEFU1-CA",
        }

        # Assumed state
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_target_temperature = 22.0
        self._attr_fan_mode = FAN_AUTO
        self._attr_current_temperature: float | None = None

        # Follow Me
        self._follow_me_enabled: bool = False
        self._follow_me_unsub = None
        self._sensor_unsub = None

    async def async_added_to_hass(self) -> None:
        """Start tracking the temperature sensor."""
        await super().async_added_to_hass()
        self._sensor_unsub = async_track_state_change_event(
            self.hass, [self._temperature_sensor], self._on_sensor_update
        )
        # Read initial sensor state
        state = self.hass.states.get(self._temperature_sensor)
        if state and state.state not in ("unknown", "unavailable"):
            try:
                self._attr_current_temperature = float(state.state)
            except ValueError:
                pass

    async def async_will_remove_from_hass(self) -> None:
        if self._sensor_unsub:
            self._sensor_unsub()
        if self._follow_me_unsub:
            self._follow_me_unsub()

    @callback
    def _on_sensor_update(self, event) -> None:
        new_state = event.data.get("new_state")
        if new_state and new_state.state not in ("unknown", "unavailable"):
            try:
                self._attr_current_temperature = float(new_state.state)
                self.async_write_ha_state()
            except ValueError:
                pass

    # ── Follow Me ─────────────────────────────────────────────────────────────

    @property
    def follow_me_enabled(self) -> bool:
        return self._follow_me_enabled

    async def async_enable_follow_me(self) -> None:
        self._follow_me_enabled = True
        await self._send_follow_me()
        self._follow_me_unsub = async_track_time_interval(
            self.hass,
            self._follow_me_tick,
            dt_util.timedelta(seconds=FOLLOW_ME_INTERVAL),
        )
        self.async_write_ha_state()

    async def async_disable_follow_me(self) -> None:
        self._follow_me_enabled = False
        if self._follow_me_unsub:
            self._follow_me_unsub()
            self._follow_me_unsub = None
        self.async_write_ha_state()

    @callback
    def _follow_me_tick(self, _now) -> None:
        self.hass.async_create_task(self._send_follow_me())

    async def _send_follow_me(self) -> None:
        temp = self._attr_current_temperature
        if temp is None:
            _LOGGER.warning("Follow Me: no temperature available from sensor")
            return
        await self._send(make_follow_me_command(temp, beep=False))

    # ── Climate control ────────────────────────────────────────────────────────

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        self._attr_hvac_mode = hvac_mode
        await self._transmit_state()
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is not None:
            self._attr_target_temperature = temp
            await self._transmit_state()
            self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        self._attr_fan_mode = fan_mode
        await self._transmit_state()
        self.async_write_ha_state()

    async def async_turn_on(self) -> None:
        if self._attr_hvac_mode == HVACMode.OFF:
            self._attr_hvac_mode = HVACMode.COOL
        await self._transmit_state()
        self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        self._attr_hvac_mode = HVACMode.OFF
        await self._transmit_state()
        self.async_write_ha_state()

    async def _transmit_state(self) -> None:
        power = self._attr_hvac_mode != HVACMode.OFF
        mode = _HVAC_TO_MIDEA.get(self._attr_hvac_mode, "auto")
        fan = self._attr_fan_mode or FAN_AUTO
        command = MideaClimateCommand(
            power=power,
            mode=mode,
            target_temp=self._attr_target_temperature or 22.0,
            fan_mode=fan,
        )
        await self._send(command)

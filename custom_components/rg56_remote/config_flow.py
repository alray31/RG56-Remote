"""Config flow for RG56 Remote."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components import infrared
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import entity_registry as er, selector

from . import CONF_INFRARED_ENTITY_ID, CONF_TEMPERATURE_SENSOR, DOMAIN


class RG56RemoteConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for RG56 Remote."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        emitter_entity_ids: list[str] = infrared.async_get_emitters(self.hass)
        if not emitter_entity_ids:
            return self.async_abort(reason="no_emitters")

        ent_reg = er.async_get(self.hass)
        emitter_options: dict[str, str] = {}
        for entity_id in emitter_entity_ids:
            entry = ent_reg.async_get(entity_id)
            label = (
                entry.name or entry.original_name or entity_id
                if entry
                else entity_id
            )
            emitter_options[entity_id] = label

        if user_input is not None:
            selected_emitter = user_input[CONF_INFRARED_ENTITY_ID]
            selected_sensor = user_input[CONF_TEMPERATURE_SENSOR]

            await self.async_set_unique_id(f"rg56_remote_{selected_emitter}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"RG56 Remote ({emitter_options.get(selected_emitter, selected_emitter)})",
                data={
                    CONF_INFRARED_ENTITY_ID: selected_emitter,
                    CONF_TEMPERATURE_SENSOR: selected_sensor,
                },
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_INFRARED_ENTITY_ID): vol.In(emitter_options),
                vol.Required(CONF_TEMPERATURE_SENSOR): selector.selector(
                    {"entity": {"domain": "sensor", "device_class": "temperature"}}
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

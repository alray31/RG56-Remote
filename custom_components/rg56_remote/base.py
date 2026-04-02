"""Shared IR send helper for RG56 Remote entities."""

from __future__ import annotations

from infrared_protocols import Command

from homeassistant.components import infrared
from homeassistant.core import HomeAssistant

from . import CONF_INFRARED_ENTITY_ID


class MideaIRMixin:
    """Mixin that provides a helper to send Midea IR commands."""

    hass: HomeAssistant
    _infrared_entity_id: str

    async def _send(self, command: Command) -> None:
        """Send a Midea IR command through the infrared building block."""
        await infrared.async_send_command(
            self.hass,
            self._infrared_entity_id,
            command,
            context=self._context if hasattr(self, "_context") else None,
        )

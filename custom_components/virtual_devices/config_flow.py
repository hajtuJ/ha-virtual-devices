"""Config flow for the Virtual Devices integration."""

from typing import TYPE_CHECKING, Any
from uuid import uuid4

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.helpers import selector

from .const import CONF_DEVICE_ID, DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigFlowResult


class VirtualDevicesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure one virtual gate per config entry."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial configuration step."""
        if user_input is not None:
            device_id = uuid4().hex
            await self.async_set_unique_id(device_id)
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data={
                    CONF_NAME: user_input[CONF_NAME],
                    CONF_DEVICE_ID: device_id,
                },
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_NAME): selector.TextSelector()}),
        )

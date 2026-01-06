"""Config flow for Climate Guard Switch integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_ALLOWED_WEATHER,
    CONF_CLIMATE_ENTITY,
    CONF_DEVICE_TYPE,
    CONF_HEARTBEAT_ENABLED,
    CONF_SUN_ENTITY,
    CONF_TARGET_ENTITY,
    CONF_WEATHER_ENTITY,
    DEVICE_TYPE_COOLER,
    DEVICE_TYPE_HEATER,
    DOMAIN,
    WEATHER_STATES,
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Climate Guard Switch."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is not None:
            # Use a simple, clean title for the Entry. 
            # This becomes the Device Name, and thus the Entity ID (switch.heater_guard).
            type_name = user_input[CONF_DEVICE_TYPE].title() # Heater or Cooler
            title = f"{type_name} Guard"
            return self.async_create_entry(title=title, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TARGET_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="switch")
                    ),
                    vol.Required(CONF_DEVICE_TYPE): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[DEVICE_TYPE_HEATER, DEVICE_TYPE_COOLER],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(CONF_SUN_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sun")
                    ),
                    vol.Optional(CONF_WEATHER_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="weather")
                    ),
                    vol.Optional(CONF_CLIMATE_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="climate")
                    ),
                    vol.Optional(CONF_ALLOWED_WEATHER): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=WEATHER_STATES,
                            multiple=True,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(CONF_HEARTBEAT_ENABLED, default=True): bool,
                }
            ),
        )

"""Config flow for Climate Guard Switch integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult, OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_ALLOWED_WEATHER,
    CONF_CLIMATE_ENTITY,
    CONF_DEVICE_TYPE,
    CONF_HEARTBEAT,
    CONF_SUN_ENTITY,
    CONF_TARGET_ENTITY,
    CONF_WEATHER_ENTITY,
    DEFAULT_HEARTBEAT,
    DEVICE_TYPE_COOLER,
    DEVICE_TYPE_HEATER,
    DOMAIN,
    WEATHER_STATES,
)


def _get_config_schema(defaults: dict[str, Any] | None = None, is_options: bool = False) -> vol.Schema:
    """Return the configuration schema with optional defaults."""
    defaults = defaults or {}
    
    schema = {}
    
    # Target Entity (Always editable)
    schema[vol.Required(
        CONF_TARGET_ENTITY,
        description={"suggested_value": defaults.get(CONF_TARGET_ENTITY)}
    )] = selector.EntitySelector(
        selector.EntitySelectorConfig(domain="switch")
    )
    
    if not is_options:
        schema[vol.Required(
            CONF_DEVICE_TYPE,
            description={"suggested_value": defaults.get(CONF_DEVICE_TYPE)}
        )] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[DEVICE_TYPE_HEATER, DEVICE_TYPE_COOLER],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )

    # Optional Gates & Links
    schema[vol.Optional(
        CONF_SUN_ENTITY,
        description={"suggested_value": defaults.get(CONF_SUN_ENTITY)}
    )] = selector.EntitySelector(
        selector.EntitySelectorConfig(domain="sun")
    )
    
    schema[vol.Optional(
        CONF_WEATHER_ENTITY,
        description={"suggested_value": defaults.get(CONF_WEATHER_ENTITY)}
    )] = selector.EntitySelector(
        selector.EntitySelectorConfig(domain="weather")
    )
    
    schema[vol.Optional(
        CONF_CLIMATE_ENTITY,
        description={"suggested_value": defaults.get(CONF_CLIMATE_ENTITY)}
    )] = selector.EntitySelector(
        selector.EntitySelectorConfig(domain="climate")
    )
    
    schema[vol.Optional(
        CONF_ALLOWED_WEATHER,
        description={"suggested_value": defaults.get(CONF_ALLOWED_WEATHER)}
    )] = selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=WEATHER_STATES,
            multiple=True,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )
    
    # Heartbeat Interval
    schema[vol.Optional(
        CONF_HEARTBEAT,
        description={"suggested_value": defaults.get(CONF_HEARTBEAT, DEFAULT_HEARTBEAT)}
    )] = vol.All(vol.Coerce(int), vol.Range(min=0))
    
    return vol.Schema(schema)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Climate Guard Switch."""

    VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_TARGET_ENTITY])
            self._abort_if_unique_id_configured()

            type_name = user_input[CONF_DEVICE_TYPE].title() # Heater or Cooler
            title = f"{type_name} Guard"
            return self.async_create_entry(title=title, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=_get_config_schema(),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user change the device type without re-adding the integration.

        Everything else (target entity, gates, heartbeat) is already editable via
        the options flow; `device_type` is the only field fixed at creation time.
        """
        reconfigure_entry = self._get_reconfigure_entry()

        if user_input is not None:
            type_name = user_input[CONF_DEVICE_TYPE].title()  # Heater or Cooler
            return self.async_update_reload_and_abort(
                reconfigure_entry,
                title=f"{type_name} Guard",
                data_updates=user_input,
            )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_DEVICE_TYPE,
                    default=reconfigure_entry.data.get(CONF_DEVICE_TYPE, DEVICE_TYPE_HEATER),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[DEVICE_TYPE_HEATER, DEVICE_TYPE_COOLER],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="reconfigure", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return OptionsFlowHandler()


class OptionsFlowHandler(OptionsFlowWithReload):
    """Climate Guard Switch options flow."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            for key in [CONF_SUN_ENTITY, CONF_WEATHER_ENTITY, CONF_CLIMATE_ENTITY, CONF_ALLOWED_WEATHER]:
                if key not in user_input:
                    user_input[key] = None

            options = {**self.config_entry.options, **user_input}
            return self.async_create_entry(title="", data=options)

        current_config = {**self.config_entry.data, **self.config_entry.options}

        return self.async_show_form(
            step_id="init",
            data_schema=_get_config_schema(current_config, is_options=True),
        )

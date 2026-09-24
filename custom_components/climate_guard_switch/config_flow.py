"""Config flow for Climate Guard Switch integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult, OptionsFlowWithReload
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_ALLOWED_WEATHER,
    CONF_CLIMATE_ENTITY,
    CONF_COOLING_ENTITY,
    CONF_DEVICE_TYPE,
    CONF_ENTRY_TYPE,
    CONF_HEARTBEAT,
    CONF_HEATING_ENTITY,
    CONF_SUN_ENTITY,
    CONF_TARGET_ENTITY,
    CONF_TEMPERATURE_SENSOR,
    CONF_WEATHER_ENTITY,
    DEFAULT_HEARTBEAT,
    DEFAULT_HISTORY_NAME,
    DEVICE_TYPE_COOLER,
    DEVICE_TYPE_HEATER,
    DOMAIN,
    ENTRY_TYPE_GUARD,
    ENTRY_TYPE_HISTORY,
    WEATHER_STATES,
)
from .history import history_config, is_history_entry


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


def _get_history_schema(defaults: dict[str, Any] | None = None, include_name: bool = False) -> vol.Schema:
    """Return the History view schema: inputs can come from any integration."""
    defaults = defaults or {}

    schema = {}

    if include_name:
        schema[vol.Required(CONF_NAME, default=DEFAULT_HISTORY_NAME)] = selector.TextSelector()

    # The temperature line is what the heating/cooling shading is drawn under,
    # so it is the one required input.
    schema[vol.Required(
        CONF_TEMPERATURE_SENSOR,
        description={"suggested_value": defaults.get(CONF_TEMPERATURE_SENSOR)}
    )] = selector.EntitySelector(
        selector.EntitySelectorConfig(domain="sensor")
    )

    schema[vol.Optional(
        CONF_CLIMATE_ENTITY,
        description={"suggested_value": defaults.get(CONF_CLIMATE_ENTITY)}
    )] = selector.EntitySelector(
        selector.EntitySelectorConfig(domain="climate")
    )

    for key in (CONF_HEATING_ENTITY, CONF_COOLING_ENTITY):
        schema[vol.Optional(
            key,
            description={"suggested_value": defaults.get(key)}
        )] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["switch", "binary_sensor", "input_boolean"])
        )

    return vol.Schema(schema)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Climate Guard Switch."""

    VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose what to add: a guard switch or a read-only history view."""
        return self.async_show_menu(
            step_id="user",
            menu_options=[ENTRY_TYPE_GUARD, ENTRY_TYPE_HISTORY],
        )

    async def async_step_guard(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the guard switch form."""
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_TARGET_ENTITY])
            self._abort_if_unique_id_configured()

            type_name = user_input[CONF_DEVICE_TYPE].title() # Heater or Cooler
            title = f"{type_name} Guard"
            return self.async_create_entry(title=title, data=user_input)

        return self.async_show_form(
            step_id="guard",
            data_schema=_get_config_schema(),
        )

    async def async_step_history(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create a read-only history view.

        No unique_id on purpose: the inputs are editable later, so an id derived
        from them would go stale, and several views (e.g. one per room)
        are legitimate.
        """
        if user_input is not None:
            data = {CONF_ENTRY_TYPE: ENTRY_TYPE_HISTORY, **user_input}
            title = data.pop(CONF_NAME).strip() or DEFAULT_HISTORY_NAME
            return self.async_create_entry(title=title, data=data)

        return self.async_show_form(
            step_id="history",
            data_schema=_get_history_schema(include_name=True),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user change the device type without re-adding the integration.

        Everything else (target entity, gates, heartbeat) is already editable via
        the options flow; `device_type` is the only field fixed at creation time.
        """
        reconfigure_entry = self._get_reconfigure_entry()

        if is_history_entry(reconfigure_entry):
            # History views have no device type; their inputs are options.
            return self.async_abort(reason="history_reconfigure")

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
        if is_history_entry(config_entry):
            return HistoryOptionsFlowHandler()
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


class HistoryOptionsFlowHandler(OptionsFlowWithReload):
    """Options flow for a History view: change which entities it mirrors."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Entry point; the form lives in its own step so its strings stay separate."""
        return await self.async_step_history(user_input)

    async def async_step_history(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the inputs."""
        if user_input is not None:
            # An optional field left empty is omitted from the submission; store
            # None so it overrides (clears) the value from the original data.
            for key in [CONF_CLIMATE_ENTITY, CONF_HEATING_ENTITY, CONF_COOLING_ENTITY]:
                if key not in user_input:
                    user_input[key] = None

            options = {**self.config_entry.options, **user_input}
            return self.async_create_entry(title="", data=options)

        return self.async_show_form(
            step_id="history",
            data_schema=_get_history_schema(history_config(self.config_entry)),
        )

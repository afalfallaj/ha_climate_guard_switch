"""Climate platform for Climate Guard Switch — the History view's chart entity.

Home Assistant's built-in History page draws ONE combined chart for a climate
entity: the current temperature, the target temperature, and shaded heating /
cooling periods. This entity exists only so that chart can be assembled from
entities of any integration, and it is strictly read-only:

- No features are advertised, so Home Assistant shows no target/fan/preset
  controls and rejects the corresponding services.
- Only the current mode is ever offered in `hvac_modes`, so Home Assistant
  rejects any other `set_hvac_mode` request before it reaches this class.
- Nothing here ever calls a service.

The target temperature is published through `extra_state_attributes` (Home
Assistant only emits `temperature` itself when the target feature is
advertised), which is enough for the history chart to draw the target line.
"""
from __future__ import annotations

import math

from homeassistant.components.climate import (
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, PRECISION_TENTHS
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    CONF_CLIMATE_ENTITY,
    CONF_COOLING_ENTITY,
    CONF_HEATING_ENTITY,
    CONF_TEMPERATURE_SENSOR,
)
from .history import (
    configured_entities,
    derive_hvac_action,
    history_config,
    history_device_info,
    mode_without_thermostat,
    read_float_attribute,
    read_temperature,
    thermostat_mode,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the read-only history climate entity."""
    async_add_entities([HistoryClimate(config_entry)])


class HistoryClimate(ClimateEntity):
    """Read-only climate entity that mirrors other entities for the history chart."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_should_poll = False
    _attr_supported_features = ClimateEntityFeature(0)
    _attr_precision = PRECISION_TENTHS

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize from the entry's configured input entities."""
        config = history_config(entry)
        self._temperature_sensor: str | None = config.get(CONF_TEMPERATURE_SENSOR)
        self._thermostat: str | None = config.get(CONF_CLIMATE_ENTITY)
        self._heating: str | None = config.get(CONF_HEATING_ENTITY)
        self._cooling: str | None = config.get(CONF_COOLING_ENTITY)
        self._tracked = configured_entities(
            config,
            CONF_TEMPERATURE_SENSOR,
            CONF_CLIMATE_ENTITY,
            CONF_HEATING_ENTITY,
            CONF_COOLING_ENTITY,
        )

        self._attr_unique_id = f"{entry.entry_id}_history"
        self._attr_device_info = history_device_info(entry)

    def _state(self, entity_id: str | None) -> State | None:
        return self.hass.states.get(entity_id) if entity_id else None

    @property
    def temperature_unit(self) -> str:
        """Report in the system unit, so Home Assistant applies no further conversion."""
        return self.hass.config.units.temperature_unit

    @property
    def current_temperature(self) -> float | None:
        """Temperature from the configured sensor, converted to the system unit."""
        return read_temperature(self.hass, self._temperature_sensor, self.temperature_unit)

    @property
    def min_temp(self) -> float:
        """Low end of the more-info dial: the thermostat's own, widened to fit the reading.

        The entity's default range is 7-35 °C, which would leave a hotter
        reading off the dial. The charts never use this.
        """
        low = read_float_attribute(self._state(self._thermostat), ATTR_MIN_TEMP)
        if low is None:
            low = super().min_temp
        current = self.current_temperature
        return low if current is None else min(low, math.floor(current))

    @property
    def max_temp(self) -> float:
        """High end of the more-info dial: the thermostat's own, widened to fit the reading."""
        high = read_float_attribute(self._state(self._thermostat), ATTR_MAX_TEMP)
        if high is None:
            high = super().max_temp
        current = self.current_temperature
        return high if current is None else max(high, math.ceil(current))

    @property
    def hvac_mode(self) -> HVACMode | None:
        """The linked thermostat's mode, or one derived from what is configured."""
        if self._thermostat:
            return thermostat_mode(self._state(self._thermostat))
        return mode_without_thermostat(bool(self._heating), bool(self._cooling))

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Only the current mode: anything else is rejected by Home Assistant."""
        mode = self.hvac_mode
        return [mode] if mode else []

    @property
    def hvac_action(self) -> HVACAction | None:
        """What the equipment is actually doing, from the real heating/cooling entities."""
        return derive_hvac_action(
            self._state(self._thermostat),
            self._state(self._heating),
            self._state(self._cooling),
            has_heating=bool(self._heating),
            has_cooling=bool(self._cooling),
        )

    @property
    def extra_state_attributes(self) -> dict[str, float] | None:
        """The thermostat's target(s), passed through so the chart can draw them."""
        thermostat = self._state(self._thermostat)
        attributes = {
            attribute: value
            for attribute in (ATTR_TEMPERATURE, ATTR_TARGET_TEMP_LOW, ATTR_TARGET_TEMP_HIGH)
            if (value := read_float_attribute(thermostat, attribute)) is not None
        }
        return attributes or None

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Do nothing: this entity is read-only.

        Home Assistant only lets a mode through if it is in `hvac_modes`, which
        holds just the current one, so there is never anything to change.
        """

    async def async_added_to_hass(self) -> None:
        """Follow every configured input entity."""
        await super().async_added_to_hass()
        if self._tracked:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, self._tracked, self._handle_source_change
                )
            )

    @callback
    def _handle_source_change(self, event: Event) -> None:
        self.async_write_ha_state()

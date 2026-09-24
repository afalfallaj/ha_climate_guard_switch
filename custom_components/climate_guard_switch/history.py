"""Helpers for the History view entry type.

A History view is a read-only mirror of entities that can come from any
integration: a temperature sensor, an optional thermostat and optional
heating/cooling entities. Everything here is a pure function of Home Assistant
states, so it can be unit-tested without a running instance. Nothing in this
module ever calls a service.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from homeassistant.components.climate import (
    ATTR_HVAC_ACTION,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.util.unit_conversion import TemperatureConverter

from .const import CONF_ENTRY_TYPE, DOMAIN, ENTRY_TYPE_HISTORY


def is_history_entry(entry: ConfigEntry) -> bool:
    """Return True for History view entries; anything else is a guard."""
    return entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_HISTORY


def history_config(entry: ConfigEntry) -> dict[str, Any]:
    """Effective config: options override data, and a None option clears a field."""
    return {**entry.data, **entry.options}


def configured_entities(config: Mapping[str, Any], *keys: str) -> list[str]:
    """Entity ids set under `keys`, skipping fields that are missing or cleared."""
    return [entity_id for key in keys if (entity_id := config.get(key))]


def history_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Device shared by every entity of one History view."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="Custom",
        model="Climate History",
    )


def source_available(state: State | None) -> bool:
    """True when the source entity exists and reports a usable state."""
    return state is not None and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)


def is_on(state: State | None) -> bool:
    """True when the source entity is on. A missing/unavailable source is not on."""
    return state is not None and state.state == STATE_ON


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def read_temperature(hass: HomeAssistant, entity_id: str | None, to_unit: str) -> float | None:
    """Read a temperature sensor's state, converted into `to_unit`.

    Returns None when the sensor is missing/unavailable, isn't numeric, or its
    unit isn't a temperature unit. A sensor with no unit is assumed to already
    be in `to_unit`.
    """
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if not source_available(state):
        return None

    value = _finite_float(state.state)
    if value is None:
        return None

    from_unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
    if not from_unit or from_unit == to_unit:
        return value
    try:
        return TemperatureConverter.convert(value, from_unit, to_unit)
    except HomeAssistantError:
        return None


def read_float_attribute(state: State | None, attribute: str) -> float | None:
    """Read a numeric attribute (e.g. a thermostat's target), None if absent/invalid."""
    if not source_available(state):
        return None
    return _finite_float(state.attributes.get(attribute))


def thermostat_mode(state: State | None) -> HVACMode | None:
    """The thermostat's HVAC mode, or None when unavailable or not a valid mode."""
    if not source_available(state):
        return None
    try:
        return HVACMode(state.state)
    except ValueError:
        return None


def mode_without_thermostat(has_heating: bool, has_cooling: bool) -> HVACMode:
    """Mode to show when no thermostat is linked, from what is configured."""
    if has_heating and has_cooling:
        return HVACMode.HEAT_COOL
    if has_heating:
        return HVACMode.HEAT
    if has_cooling:
        return HVACMode.COOL
    return HVACMode.OFF


def derive_hvac_action(
    thermostat: State | None,
    heating: State | None,
    cooling: State | None,
    *,
    has_heating: bool,
    has_cooling: bool,
) -> HVACAction | None:
    """What the equipment is actually doing, judged from the real relays.

    The relays are the ground truth, so a relay that is on wins even if the
    thermostat says it is off. With no relays configured there is nothing to
    judge from, so the thermostat's own hvac_action is mirrored instead.
    """
    if not has_heating and not has_cooling:
        if not source_available(thermostat):
            return None
        try:
            return HVACAction(thermostat.attributes.get(ATTR_HVAC_ACTION))
        except ValueError:
            return None

    if has_heating and is_on(heating):
        return HVACAction.HEATING
    if has_cooling and is_on(cooling):
        return HVACAction.COOLING
    if thermostat_mode(thermostat) == HVACMode.OFF:
        return HVACAction.OFF

    relays = ((has_heating, heating), (has_cooling, cooling))
    if not any(source_available(state) for configured, state in relays if configured):
        return None
    return HVACAction.IDLE

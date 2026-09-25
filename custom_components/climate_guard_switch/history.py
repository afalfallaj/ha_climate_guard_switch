"""Helpers for the guard's history chart sensors.

Home Assistant draws values of one kind per chart and keeps long-term statistics
only for sensors, so the guard publishes its thermostat's target and "the
temperature while the relay ran" as temperature sensors. Everything here is a
pure function of Home Assistant states, so it can be unit-tested without a
running instance. Nothing in this module ever calls a service.
"""
from __future__ import annotations

import math
from typing import Any

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
    """True for a leftover "History view" entry from v0.0.4–v0.0.6 (no longer supported)."""
    return entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_HISTORY


def guard_device_info(entry: ConfigEntry) -> DeviceInfo:
    """The guard's device, shared by every entity of one config entry."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="Custom",
        model="Climate Guard Switch",
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


def trace_temperature(
    hass: HomeAssistant, temperature_sensor: str | None, activity: State | None, to_unit: str
) -> float | None:
    """The temperature while `activity` is on; None (an empty trace) while it is off.

    A temperature that exists only while the equipment ran is how a relay's
    on/off periods can be shown in the temperature chart for any date range.
    """
    if not is_on(activity):
        return None
    return read_temperature(hass, temperature_sensor, to_unit)

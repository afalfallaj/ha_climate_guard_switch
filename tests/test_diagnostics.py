"""Tests for custom_components/climate_guard_switch/diagnostics.py.

History views have no coordinator, so they get their own snapshot; the guard
snapshot shape is pinned here too, since the History branch sits in front of it.
"""
from __future__ import annotations

from custom_components.climate_guard_switch.const import (
    CONF_CLIMATE_ENTITY,
    CONF_ENTRY_TYPE,
    CONF_HEATING_ENTITY,
    CONF_TARGET_ENTITY,
    CONF_TEMPERATURE_SENSOR,
    ENTRY_TYPE_HISTORY,
)
from custom_components.climate_guard_switch.coordinator import ClimateGuardCoordinator
from custom_components.climate_guard_switch.diagnostics import async_get_config_entry_diagnostics

from conftest import _ConfigEntry, _HomeAssistant  # type: ignore[import]


def _history_entry(**options) -> _ConfigEntry:
    return _ConfigEntry(
        data={
            CONF_ENTRY_TYPE: ENTRY_TYPE_HISTORY,
            CONF_TEMPERATURE_SENSOR: "sensor.water_temp",
            CONF_CLIMATE_ENTITY: "climate.water_thermostat",
            CONF_HEATING_ENTITY: "switch.heat",
        },
        options=options,
    )


async def test_history_diagnostics_lists_config_and_the_state_of_each_input() -> None:
    hass = _HomeAssistant()
    hass.states.set("sensor.water_temp", "41.2")
    hass.states.set("climate.water_thermostat", "heat", {"temperature": 55.0})

    result = await async_get_config_entry_diagnostics(hass, _history_entry())

    assert set(result) == {"config", "related_entities"}
    assert result["config"][CONF_TEMPERATURE_SENSOR] == "sensor.water_temp"
    assert result["related_entities"]["temperature_sensor"]["state"] == "41.2"
    assert result["related_entities"]["thermostat"]["attributes"] == {"temperature": 55.0}
    # Configured but not in the state machine: reported, not a crash.
    assert result["related_entities"]["heating"] == {"state": "unknown", "entity_id": "switch.heat"}
    # Never configured: no entry to report.
    assert result["related_entities"]["cooling"] is None


async def test_history_diagnostics_respects_inputs_cleared_in_options() -> None:
    hass = _HomeAssistant()

    result = await async_get_config_entry_diagnostics(hass, _history_entry(**{CONF_HEATING_ENTITY: None}))

    assert result["related_entities"]["heating"] is None


async def test_guard_diagnostics_shape_is_unchanged() -> None:
    hass = _HomeAssistant()
    entry = _ConfigEntry(data={CONF_TARGET_ENTITY: "switch.heater"})
    entry.runtime_data = ClimateGuardCoordinator(hass, entry)

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert set(result) == {"config", "runtime_limits", "related_entities"}
    assert result["config"][CONF_TARGET_ENTITY] == "**REDACTED**"
    assert set(result["related_entities"]) == {"target", "sun", "weather", "climate"}
    assert result["runtime_limits"]["guard_enabled"] is False

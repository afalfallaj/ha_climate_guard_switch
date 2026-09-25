"""Tests for custom_components/climate_guard_switch/diagnostics.py."""
from __future__ import annotations

from custom_components.climate_guard_switch.const import (
    CONF_CLIMATE_ENTITY,
    CONF_TARGET_ENTITY,
    CONF_TEMPERATURE_SENSOR,
)
from custom_components.climate_guard_switch.coordinator import ClimateGuardCoordinator
from custom_components.climate_guard_switch.diagnostics import async_get_config_entry_diagnostics

from conftest import _ConfigEntry, _HomeAssistant  # type: ignore[import]


async def test_guard_diagnostics_shape_and_redaction() -> None:
    hass = _HomeAssistant()
    hass.states.set("sensor.room_temperature", "41.2")
    entry = _ConfigEntry(
        data={
            CONF_TARGET_ENTITY: "switch.heater",
            CONF_CLIMATE_ENTITY: "climate.room_thermostat",
            CONF_TEMPERATURE_SENSOR: "sensor.room_temperature",
        }
    )
    entry.runtime_data = ClimateGuardCoordinator(hass, entry)

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert set(result) == {"config", "runtime_limits", "related_entities"}
    assert result["config"][CONF_TARGET_ENTITY] == "**REDACTED**"
    assert set(result["related_entities"]) == {"target", "sun", "weather", "climate", "temperature_sensor"}
    assert result["related_entities"]["temperature_sensor"]["state"] == "41.2"
    # Configured but not in the state machine: reported, not a crash.
    assert result["related_entities"]["climate"] == {"state": "unknown", "entity_id": "climate.room_thermostat"}
    # Never configured: no entry to report.
    assert result["related_entities"]["sun"] is None
    assert result["runtime_limits"]["guard_enabled"] is False

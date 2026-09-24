"""Tests for the History view: helpers (history.py) and its sensors (sensor.py).

The History view mirrors entities from any integration into temperature sensors
that Home Assistant's built-in cards can draw together, so everything here is
driven by plain states in the fake state machine. What matters most: a trace is
the temperature only while its relay is on (never a made-up value), the sensors
are hidden/diagnostic where the design says so, and nothing ever calls a service.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.climate_guard_switch import sensor as sensor_platform
from custom_components.climate_guard_switch.const import (
    CONF_CLIMATE_ENTITY,
    CONF_COOLING_ENTITY,
    CONF_ENTRY_TYPE,
    CONF_HEATING_ENTITY,
    CONF_TARGET_ENTITY,
    CONF_TEMPERATURE_SENSOR,
    ENTRY_TYPE_HISTORY,
)
from custom_components.climate_guard_switch.history import (
    history_config,
    history_device_info,
    is_history_entry,
    is_on,
    read_float_attribute,
    read_temperature,
    source_available,
    trace_temperature,
)
from custom_components.climate_guard_switch.sensor import (
    GuardStatusSensor,
    HistoryTargetTemperatureSensor,
    HistoryTraceSensor,
    _history_sensors,
)

from conftest import _ConfigEntry, _HomeAssistant, _State  # type: ignore[import]

TEMPERATURE = "sensor.room_temperature"
THERMOSTAT = "climate.room_thermostat"
HEATING = "switch.heat"
COOLING = "switch.cool"

FULL = {
    CONF_TEMPERATURE_SENSOR: TEMPERATURE,
    CONF_CLIMATE_ENTITY: THERMOSTAT,
    CONF_HEATING_ENTITY: HEATING,
    CONF_COOLING_ENTITY: COOLING,
}


def _hass(unit: str = "°C") -> _HomeAssistant:
    hass = _HomeAssistant()
    hass.config.units.temperature_unit = unit
    return hass


def _state(state: str, **attributes) -> _State:
    return _State(state, attributes)


def _entry(config: dict | None = None, **options) -> _ConfigEntry:
    return _ConfigEntry(
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_HISTORY, **(FULL if config is None else config)},
        options=options,
        entry_id="hist1",
        title="Room History",
    )


def _sensor(cls, entry_config: dict | None = None, *args, hass: _HomeAssistant | None = None):
    sensor = cls(_entry(entry_config), *args)
    sensor.hass = hass or _hass()
    return sensor


ON = _state("on")
OFF = _state("off")
UNAVAILABLE = _state("unavailable")


# ---------------------------------------------------------------------------
# history.py — entry helpers
# ---------------------------------------------------------------------------


def test_only_history_typed_entries_are_history_entries() -> None:
    assert is_history_entry(_entry())
    assert not is_history_entry(_ConfigEntry(data={CONF_TARGET_ENTITY: "switch.heater"}))
    assert not is_history_entry(_ConfigEntry(data={CONF_ENTRY_TYPE: "guard"}))


def test_history_config_lets_options_override_data_and_none_clears_a_field() -> None:
    entry = _entry(**{CONF_HEATING_ENTITY: None, CONF_TEMPERATURE_SENSOR: "sensor.other"})

    config = history_config(entry)

    assert config[CONF_HEATING_ENTITY] is None
    assert config[CONF_TEMPERATURE_SENSOR] == "sensor.other"
    assert config[CONF_COOLING_ENTITY] == COOLING  # untouched


def test_device_info_groups_every_entity_under_one_device() -> None:
    info = history_device_info(_entry())

    assert info["identifiers"] == {("climate_guard_switch", "hist1")}
    assert info["name"] == "Room History"
    assert info["model"] == "Climate History"


# ---------------------------------------------------------------------------
# history.py — state readers
# ---------------------------------------------------------------------------


def test_source_available_and_is_on() -> None:
    assert source_available(_state("21.5"))
    assert not source_available(_state("unavailable"))
    assert not source_available(_state("unknown"))
    assert not source_available(None)

    assert is_on(ON)
    assert not is_on(OFF)
    assert not is_on(UNAVAILABLE)
    assert not is_on(None)


@pytest.mark.parametrize(
    ("state", "attributes", "to_unit", "expected"),
    [
        ("21.5", {}, "°C", 21.5),  # no unit: assumed to already be in the target unit
        ("21.5", {"unit_of_measurement": "°C"}, "°C", 21.5),
        ("70", {"unit_of_measurement": "°F"}, "°C", pytest.approx(21.111, abs=1e-3)),
        ("21", {"unit_of_measurement": "°C"}, "°F", pytest.approx(69.8)),
        ("294.15", {"unit_of_measurement": "K"}, "°C", pytest.approx(21.0)),
        ("unavailable", {}, "°C", None),
        ("unknown", {}, "°C", None),
        ("warm", {}, "°C", None),
        ("nan", {}, "°C", None),
        ("inf", {}, "°C", None),
        ("55", {"unit_of_measurement": "%"}, "°C", None),  # not a temperature unit
    ],
)
def test_read_temperature(state, attributes, to_unit, expected) -> None:
    hass = _hass(to_unit)
    hass.states.set(TEMPERATURE, state, attributes)

    assert read_temperature(hass, TEMPERATURE, to_unit) == expected


def test_read_temperature_handles_missing_and_unconfigured_sensors() -> None:
    hass = _hass()

    assert read_temperature(hass, "sensor.absent", "°C") is None
    assert read_temperature(hass, None, "°C") is None


def test_read_float_attribute() -> None:
    assert read_float_attribute(_state("heat", temperature=21.5), "temperature") == 21.5
    assert read_float_attribute(_state("heat", temperature="22"), "temperature") == 22.0
    assert read_float_attribute(_state("heat", temperature=None), "temperature") is None
    assert read_float_attribute(_state("heat"), "temperature") is None
    assert read_float_attribute(_state("heat", temperature="warm"), "temperature") is None
    assert read_float_attribute(_state("unavailable", temperature=21), "temperature") is None
    assert read_float_attribute(None, "temperature") is None


def test_trace_temperature_is_the_temperature_only_while_on() -> None:
    hass = _hass()
    hass.states.set(TEMPERATURE, "21.5", {"unit_of_measurement": "°C"})

    assert trace_temperature(hass, TEMPERATURE, ON, "°C") == 21.5
    assert trace_temperature(hass, TEMPERATURE, OFF, "°C") is None
    assert trace_temperature(hass, TEMPERATURE, UNAVAILABLE, "°C") is None
    assert trace_temperature(hass, TEMPERATURE, None, "°C") is None


def test_trace_temperature_is_converted_and_empty_while_the_sensor_is_unusable() -> None:
    hass = _hass()
    hass.states.set(TEMPERATURE, "70", {"unit_of_measurement": "°F"})
    assert trace_temperature(hass, TEMPERATURE, ON, "°C") == pytest.approx(21.111, abs=1e-3)

    hass.states.set(TEMPERATURE, "unavailable")
    assert trace_temperature(hass, TEMPERATURE, ON, "°C") is None


# ---------------------------------------------------------------------------
# sensor.py — the History view's sensors
# ---------------------------------------------------------------------------


def test_one_sensor_is_created_per_configured_optional_input() -> None:
    sensors = _history_sensors(_entry())

    assert [type(s) for s in sensors] == [
        HistoryTargetTemperatureSensor,
        HistoryTraceSensor,
        HistoryTraceSensor,
    ]
    assert [s._attr_unique_id for s in sensors] == [
        "hist1_target_temperature",
        "hist1_temperature_while_heating",
        "hist1_temperature_while_cooling",
    ]
    assert [s._attr_translation_key for s in sensors] == [
        "target_temperature",
        "temperature_while_heating",
        "temperature_while_cooling",
    ]


def test_no_sensors_for_unconfigured_inputs() -> None:
    # The source temperature sensor already has its own long-term statistics: no mirror.
    assert _history_sensors(_entry({CONF_TEMPERATURE_SENSOR: TEMPERATURE})) == []
    only_heating = _history_sensors(_entry({CONF_TEMPERATURE_SENSOR: TEMPERATURE, CONF_HEATING_ENTITY: HEATING}))
    assert [s._attr_unique_id for s in only_heating] == ["hist1_temperature_while_heating"]


def test_an_input_cleared_in_options_no_longer_gets_a_sensor() -> None:
    sensors = _history_sensors(_entry(**{CONF_COOLING_ENTITY: None}))

    assert [s._attr_unique_id for s in sensors] == ["hist1_target_temperature", "hist1_temperature_while_heating"]


@pytest.mark.parametrize("unit", ["°C", "°F"])
def test_every_history_sensor_is_a_temperature_measurement_in_the_system_unit(unit) -> None:
    """Same unit and device class as the temperature: that is what puts them in its chart."""
    for sensor in _history_sensors(_entry()):
        sensor.hass = _hass(unit)
        assert sensor._attr_state_class == "measurement"  # long-term statistics
        assert sensor._attr_device_class == "temperature"
        assert sensor.native_unit_of_measurement == unit
        assert sensor._attr_has_entity_name is True
        assert sensor._attr_should_poll is False
        assert sensor._attr_device_info["identifiers"] == {("climate_guard_switch", "hist1")}


def test_target_temperature_sensor_reads_the_thermostats_target() -> None:
    hass = _hass()
    hass.states.set(THERMOSTAT, "heat", {"temperature": 55.0})
    sensor = _sensor(HistoryTargetTemperatureSensor, None, THERMOSTAT, hass=hass)

    assert sensor.native_value == 55.0
    assert sensor.available is True


def test_target_temperature_sensor_has_no_value_in_range_mode() -> None:
    hass = _hass()
    hass.states.set(THERMOSTAT, "heat_cool", {"temperature": None, "target_temp_low": 20.0})
    sensor = _sensor(HistoryTargetTemperatureSensor, None, THERMOSTAT, hass=hass)

    assert sensor.native_value is None


def test_target_temperature_sensor_is_visible_and_not_diagnostic() -> None:
    sensor = _sensor(HistoryTargetTemperatureSensor, None, THERMOSTAT)

    assert getattr(sensor, "_attr_entity_registry_visible_default", True) is True
    assert getattr(sensor, "_attr_entity_category", None) is None


@pytest.mark.parametrize("state", ["unavailable", "unknown", None])
def test_history_sensors_are_unavailable_while_their_source_is(state) -> None:
    hass = _hass()
    if state is not None:
        hass.states.set(THERMOSTAT, state, {"temperature": 55.0})
        hass.states.set(HEATING, state)
    hass.states.set(TEMPERATURE, "21.5", {"unit_of_measurement": "°C"})
    target = _sensor(HistoryTargetTemperatureSensor, None, THERMOSTAT, hass=hass)
    heating = _sensor(HistoryTraceSensor, None, TEMPERATURE, HEATING, "temperature_while_heating", hass=hass)

    assert target.available is False
    assert heating.available is False


def test_trace_sensor_value_and_availability() -> None:
    hass = _hass()
    hass.states.set(TEMPERATURE, "21.5", {"unit_of_measurement": "°C"})
    hass.states.set(HEATING, "on")
    sensor = _sensor(HistoryTraceSensor, None, TEMPERATURE, HEATING, "temperature_while_heating", hass=hass)

    assert sensor.native_value == 21.5
    assert sensor.available is True

    hass.states.set(HEATING, "off")
    assert sensor.native_value is None  # state "unknown": an empty trace, never a made-up value
    assert sensor.available is True

    hass.states.set(HEATING, "on")
    hass.states.set(TEMPERATURE, "unavailable")
    assert sensor.available is False


def test_trace_sensors_are_plain_visible_sensors() -> None:
    heating = _sensor(HistoryTraceSensor, None, TEMPERATURE, HEATING, "temperature_while_heating")
    cooling = _sensor(HistoryTraceSensor, None, TEMPERATURE, COOLING, "temperature_while_cooling")

    for sensor in (heating, cooling):
        assert getattr(sensor, "_attr_entity_category", None) is None
        assert getattr(sensor, "_attr_entity_registry_visible_default", True) is True
    assert heating._attr_icon == "mdi:thermometer-chevron-up"
    assert cooling._attr_icon == "mdi:thermometer-chevron-down"


async def test_target_sensor_follows_only_the_thermostat() -> None:
    sensor = _sensor(HistoryTargetTemperatureSensor, None, THERMOSTAT)

    with patch("custom_components.climate_guard_switch.sensor.async_track_state_change_event") as track:
        await sensor.async_added_to_hass()

    track.assert_called_once_with(sensor.hass, [THERMOSTAT], sensor._handle_source_change)
    assert sensor.removers == [track.return_value]  # unsubscribed when the entity is removed


async def test_trace_sensor_follows_both_of_its_sources() -> None:
    sensor = _sensor(HistoryTraceSensor, None, TEMPERATURE, HEATING, "temperature_while_heating")

    with patch("custom_components.climate_guard_switch.sensor.async_track_state_change_event") as track:
        await sensor.async_added_to_hass()

    track.assert_called_once_with(sensor.hass, [TEMPERATURE, HEATING], sensor._handle_source_change)


def test_a_source_change_rewrites_the_state_without_any_service_call() -> None:
    sensor = _sensor(HistoryTraceSensor, None, TEMPERATURE, HEATING, "temperature_while_heating")

    sensor._handle_source_change(MagicMock())

    assert sensor.state_writes == 1
    sensor.hass.services.async_call.assert_not_called()


async def test_sensor_platform_adds_history_sensors_and_no_status_sensor_for_history_entries() -> None:
    add = MagicMock()

    await sensor_platform.async_setup_entry(_hass(), _entry(), add)

    (added,), _ = add.call_args
    assert len(added) == 3
    assert not any(isinstance(s, GuardStatusSensor) for s in added)


async def test_sensor_platform_still_adds_only_the_status_sensor_for_guard_entries() -> None:
    """Regression: the guard path must be exactly what it was before History views."""
    guard = _ConfigEntry(data={CONF_TARGET_ENTITY: "switch.heater"}, entry_id="g1")
    guard.runtime_data = MagicMock()
    add = MagicMock()

    await sensor_platform.async_setup_entry(_hass(), guard, add)

    (added,), _ = add.call_args
    assert len(added) == 1
    assert isinstance(added[0], GuardStatusSensor)

"""Tests for the guard's history chart sensors: helpers (history.py) and sensor.py.

The sensors turn what the guard already knows (its relay, device type, linked
thermostat and an optional temperature sensor) into temperature sensors that
Home Assistant's built-in cards can draw together. Everything here is driven by
plain states in the fake state machine. What matters most: a trace is the
temperature only while the relay is on (never a made-up value), the sensors read
the real relay and never call a service, and the guard's own Status sensor is
untouched.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.climate_guard_switch import sensor as sensor_platform
from custom_components.climate_guard_switch.const import (
    CONF_CLIMATE_ENTITY,
    CONF_DEVICE_TYPE,
    CONF_ENTRY_TYPE,
    CONF_TARGET_ENTITY,
    CONF_TEMPERATURE_SENSOR,
    DEVICE_TYPE_COOLER,
    DEVICE_TYPE_HEATER,
    ENTRY_TYPE_HISTORY,
)
from custom_components.climate_guard_switch.history import (
    guard_device_info,
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
    _chart_sensors,
)

from conftest import _ConfigEntry, _HomeAssistant, _State  # type: ignore[import]

RELAY = "switch.heater_relay"
TEMPERATURE = "sensor.room_temperature"
THERMOSTAT = "climate.room_thermostat"

FULL = {
    CONF_TARGET_ENTITY: RELAY,
    CONF_DEVICE_TYPE: DEVICE_TYPE_HEATER,
    CONF_CLIMATE_ENTITY: THERMOSTAT,
    CONF_TEMPERATURE_SENSOR: TEMPERATURE,
}


def _hass(unit: str = "°C") -> _HomeAssistant:
    hass = _HomeAssistant()
    hass.config.units.temperature_unit = unit
    return hass


def _state(state: str, **attributes) -> _State:
    return _State(state, attributes)


def _entry(config: dict | None = None, **options) -> _ConfigEntry:
    return _ConfigEntry(
        data=FULL if config is None else config,
        options=options,
        entry_id="guard1",
        title="Heater Guard",
    )


def _trace(hass: _HomeAssistant, config: dict | None = None, **options) -> HistoryTraceSensor:
    sensors = [s for s in _chart_sensors(_entry(config, **options)) if isinstance(s, HistoryTraceSensor)]
    assert len(sensors) == 1
    sensors[0].hass = hass
    return sensors[0]


ON = _state("on")
OFF = _state("off")
UNAVAILABLE = _state("unavailable")


# ---------------------------------------------------------------------------
# history.py — helpers
# ---------------------------------------------------------------------------


def test_only_leftover_history_entries_are_detected() -> None:
    assert is_history_entry(_ConfigEntry(data={CONF_ENTRY_TYPE: ENTRY_TYPE_HISTORY}))
    assert not is_history_entry(_entry())
    assert not is_history_entry(_ConfigEntry(data={CONF_ENTRY_TYPE: "guard"}))


def test_device_info_is_the_guards_device() -> None:
    info = guard_device_info(_entry())

    assert info["identifiers"] == {("climate_guard_switch", "guard1")}
    assert info["name"] == "Heater Guard"
    assert info["model"] == "Climate Guard Switch"


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
# sensor.py — which chart sensors a guard gets
# ---------------------------------------------------------------------------


def test_a_fully_configured_heater_guard_gets_target_and_temperature_while_heating() -> None:
    sensors = _chart_sensors(_entry())

    assert [type(s) for s in sensors] == [HistoryTargetTemperatureSensor, HistoryTraceSensor]
    assert [s._attr_unique_id for s in sensors] == ["guard1_target_temperature", "guard1_temperature_while_running"]
    assert [s._attr_translation_key for s in sensors] == ["target_temperature", "temperature_while_heating"]
    assert sensors[1]._attr_icon == "mdi:thermometer-chevron-up"


def test_a_cooler_guard_gets_temperature_while_cooling_with_the_same_unique_id() -> None:
    sensors = _chart_sensors(_entry({**FULL, CONF_DEVICE_TYPE: DEVICE_TYPE_COOLER}))

    trace = sensors[1]
    assert trace._attr_unique_id == "guard1_temperature_while_running"  # stable across a device-type change
    assert trace._attr_translation_key == "temperature_while_cooling"
    assert trace._attr_icon == "mdi:thermometer-chevron-down"


def test_no_thermostat_means_no_target_sensor() -> None:
    sensors = _chart_sensors(_entry({CONF_TARGET_ENTITY: RELAY, CONF_DEVICE_TYPE: DEVICE_TYPE_HEATER, CONF_TEMPERATURE_SENSOR: TEMPERATURE}))

    assert [type(s) for s in sensors] == [HistoryTraceSensor]


def test_no_temperature_source_means_no_trace_sensor() -> None:
    assert _chart_sensors(_entry({CONF_TARGET_ENTITY: RELAY, CONF_DEVICE_TYPE: DEVICE_TYPE_HEATER})) == []
    # the thermostat alone is a temperature source (its current temperature)
    only_thermostat = _chart_sensors(_entry({CONF_TARGET_ENTITY: RELAY, CONF_CLIMATE_ENTITY: THERMOSTAT}))
    assert [type(s) for s in only_thermostat] == [HistoryTargetTemperatureSensor, HistoryTraceSensor]


def test_options_override_data_and_none_clears_an_input() -> None:
    # clearing the thermostat in Configure: no target sensor, the trace still has the sensor
    sensors = _chart_sensors(_entry(**{CONF_CLIMATE_ENTITY: None}))
    assert [type(s) for s in sensors] == [HistoryTraceSensor]
    # clearing the temperature sensor: the trace falls back to the thermostat
    sensors = _chart_sensors(_entry(**{CONF_TEMPERATURE_SENSOR: None}))
    assert [type(s) for s in sensors] == [HistoryTargetTemperatureSensor, HistoryTraceSensor]
    # clearing both: no trace
    assert _chart_sensors(_entry(**{CONF_TEMPERATURE_SENSOR: None, CONF_CLIMATE_ENTITY: None})) == []


@pytest.mark.parametrize("unit", ["°C", "°F"])
def test_every_chart_sensor_is_a_visible_temperature_measurement_in_the_system_unit(unit) -> None:
    """Same unit and device class as the temperature: that is what puts them in its chart."""
    for sensor in _chart_sensors(_entry()):
        sensor.hass = _hass(unit)
        assert sensor._attr_state_class == "measurement"  # long-term statistics
        assert sensor._attr_device_class == "temperature"
        assert sensor.native_unit_of_measurement == unit
        assert sensor._attr_has_entity_name is True
        assert sensor._attr_should_poll is False
        assert sensor._attr_device_info["identifiers"] == {("climate_guard_switch", "guard1")}
        assert getattr(sensor, "_attr_entity_category", None) is None
        assert getattr(sensor, "_attr_entity_registry_visible_default", True) is True


# ---------------------------------------------------------------------------
# sensor.py — values and availability
# ---------------------------------------------------------------------------


def test_target_temperature_sensor_reads_the_thermostats_target() -> None:
    hass = _hass()
    hass.states.set(THERMOSTAT, "heat", {"temperature": 55.0})
    sensor = _chart_sensors(_entry())[0]
    sensor.hass = hass

    assert sensor.native_value == 55.0
    assert sensor.available is True

    hass.states.set(THERMOSTAT, "heat_cool", {"temperature": None, "target_temp_low": 20.0})
    assert sensor.native_value is None  # range mode: no single target
    hass.states.set(THERMOSTAT, "unavailable", {"temperature": 55.0})
    assert sensor.available is False


def test_trace_from_the_temperature_sensor_follows_the_relay() -> None:
    hass = _hass()
    hass.states.set(TEMPERATURE, "21.5", {"unit_of_measurement": "°C"})
    hass.states.set(RELAY, "on")
    sensor = _trace(hass)

    assert sensor.native_value == 21.5
    assert sensor.available is True

    hass.states.set(RELAY, "off")
    assert sensor.native_value is None  # state "unknown": an empty trace, never a made-up value
    assert sensor.available is True

    hass.states.set(RELAY, "unavailable")
    assert sensor.available is False
    hass.states.set(RELAY, "on")
    hass.states.set(TEMPERATURE, "unavailable")
    assert sensor.available is False


def test_trace_falls_back_to_the_thermostats_current_temperature() -> None:
    hass = _hass()
    hass.states.set(THERMOSTAT, "heat", {"temperature": 55.0, "current_temperature": 41.2})
    hass.states.set(RELAY, "on")
    sensor = _trace(hass, **{CONF_TEMPERATURE_SENSOR: None})

    assert sensor.native_value == 41.2
    hass.states.set(RELAY, "off")
    assert sensor.native_value is None
    hass.states.set(RELAY, "on")
    hass.states.set(THERMOSTAT, "heat", {"temperature": 55.0})  # thermostat without a reading
    assert sensor.native_value is None
    hass.states.set(THERMOSTAT, "unavailable")
    assert sensor.available is False


def test_an_explicit_temperature_sensor_wins_over_the_thermostat() -> None:
    hass = _hass()
    hass.states.set(TEMPERATURE, "21.5", {"unit_of_measurement": "°C"})
    hass.states.set(THERMOSTAT, "heat", {"current_temperature": 41.2})
    hass.states.set(RELAY, "on")

    assert _trace(hass).native_value == 21.5


async def test_chart_sensors_follow_their_sources_and_rewrite_on_change() -> None:
    hass = _hass()
    target, trace = _chart_sensors(_entry())
    target.hass = trace.hass = hass

    with patch("custom_components.climate_guard_switch.sensor.async_track_state_change_event") as track:
        await target.async_added_to_hass()
        await trace.async_added_to_hass()

    assert track.call_args_list[0].args[1] == [THERMOSTAT]
    assert track.call_args_list[1].args[1] == [TEMPERATURE, RELAY]
    assert target.removers == [track.return_value]  # unsubscribed when the entity is removed

    trace._handle_source_change(MagicMock())
    assert trace.state_writes == 1
    hass.services.async_call.assert_not_called()  # read-only: never a service call


async def test_trace_without_a_sensor_follows_the_thermostat_and_the_relay() -> None:
    trace = _trace(_hass(), **{CONF_TEMPERATURE_SENSOR: None})

    with patch("custom_components.climate_guard_switch.sensor.async_track_state_change_event") as track:
        await trace.async_added_to_hass()

    assert track.call_args.args[1] == [THERMOSTAT, RELAY]


async def test_sensor_platform_adds_the_status_sensor_and_the_chart_sensors() -> None:
    entry = _entry()
    entry.runtime_data = MagicMock()
    add = MagicMock()

    await sensor_platform.async_setup_entry(_hass(), entry, add)

    (added,), _ = add.call_args
    assert [type(s) for s in added] == [GuardStatusSensor, HistoryTargetTemperatureSensor, HistoryTraceSensor]


async def test_sensor_platform_adds_only_the_status_sensor_for_a_minimal_guard() -> None:
    """Regression: a guard without thermostat or temperature sensor is exactly what it was."""
    guard = _ConfigEntry(data={CONF_TARGET_ENTITY: RELAY}, entry_id="g1")
    guard.runtime_data = MagicMock()
    add = MagicMock()

    await sensor_platform.async_setup_entry(_hass(), guard, add)

    (added,), _ = add.call_args
    assert len(added) == 1
    assert isinstance(added[0], GuardStatusSensor)

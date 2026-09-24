"""Tests for the History view: helpers (history.py), the read-only climate entity
(climate.py) and the statistics sensors (sensor.py).

The History view mirrors entities from any integration, so everything here is
driven by plain states in the fake state machine. The properties that matter most
are the read-only guarantees (no features, a single offered mode, no service
calls) and that heating/cooling reflect the *real* relays.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from homeassistant.components.climate import ClimateEntityFeature, HVACAction, HVACMode

from custom_components.climate_guard_switch import climate as climate_platform
from custom_components.climate_guard_switch import sensor as sensor_platform
from custom_components.climate_guard_switch.climate import HistoryClimate
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
    configured_entities,
    derive_hvac_action,
    history_config,
    history_device_info,
    is_history_entry,
    is_on,
    mode_without_thermostat,
    read_float_attribute,
    read_temperature,
    source_available,
    thermostat_mode,
)
from custom_components.climate_guard_switch.sensor import (
    GuardStatusSensor,
    HistoryActivitySensor,
    HistoryTargetTemperatureSensor,
    _history_sensors,
)

from conftest import _ConfigEntry, _HomeAssistant, _State  # type: ignore[import]

TEMPERATURE = "sensor.water_temp"
THERMOSTAT = "climate.water_thermostat"
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
        title="Water History",
    )


def _climate(hass: _HomeAssistant | None = None, config: dict | None = None) -> HistoryClimate:
    entity = HistoryClimate(_entry(config))
    entity.hass = hass or _hass()
    return entity


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


def test_configured_entities_skips_missing_cleared_and_empty_fields() -> None:
    config = {"a": "sensor.a", "b": None, "c": ""}

    assert configured_entities(config, "a", "b", "c", "d") == ["sensor.a"]


def test_device_info_groups_every_entity_under_one_device() -> None:
    info = history_device_info(_entry())

    assert info["identifiers"] == {("climate_guard_switch", "hist1")}
    assert info["name"] == "Water History"
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


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (_state("heat"), HVACMode.HEAT),
        (_state("off"), HVACMode.OFF),
        (_state("heat_cool"), HVACMode.HEAT_COOL),
        (_state("unavailable"), None),
        (_state("unknown"), None),
        (_state("not-a-mode"), None),
        (None, None),
    ],
)
def test_thermostat_mode(state, expected) -> None:
    assert thermostat_mode(state) == expected


@pytest.mark.parametrize(
    ("has_heating", "has_cooling", "expected"),
    [
        (True, True, HVACMode.HEAT_COOL),
        (True, False, HVACMode.HEAT),
        (False, True, HVACMode.COOL),
        (False, False, HVACMode.OFF),
    ],
)
def test_mode_without_thermostat(has_heating, has_cooling, expected) -> None:
    assert mode_without_thermostat(has_heating, has_cooling) == expected


# ---------------------------------------------------------------------------
# history.py — what the equipment is doing, judged from the real relays
# ---------------------------------------------------------------------------


def _action(thermostat=None, heating=None, cooling=None, *, has_heating=True, has_cooling=True):
    return derive_hvac_action(
        thermostat, heating, cooling, has_heating=has_heating, has_cooling=has_cooling
    )


def test_heating_relay_on_means_heating() -> None:
    assert _action(_state("heat"), ON, OFF) == HVACAction.HEATING


def test_cooling_relay_on_means_cooling() -> None:
    assert _action(_state("cool"), OFF, ON) == HVACAction.COOLING


def test_heating_wins_when_both_relays_are_on() -> None:
    assert _action(_state("heat_cool"), ON, ON) == HVACAction.HEATING


def test_a_running_relay_wins_over_a_thermostat_that_says_off() -> None:
    """The relay is the ground truth: it can still be on for a moment after the thermostat turned off."""
    assert _action(_state("off"), ON, OFF) == HVACAction.HEATING


def test_idle_when_relays_are_off_and_the_thermostat_is_active() -> None:
    assert _action(_state("heat"), OFF, OFF) == HVACAction.IDLE


def test_off_when_relays_are_off_and_the_thermostat_is_off() -> None:
    assert _action(_state("off"), OFF, OFF) == HVACAction.OFF


def test_no_action_when_every_configured_relay_is_unavailable() -> None:
    assert _action(_state("heat"), UNAVAILABLE, UNAVAILABLE) is None


def test_a_relay_missing_from_the_state_machine_counts_as_unavailable() -> None:
    assert _action(_state("heat"), None, None) is None


def test_thermostat_off_is_still_reported_when_relays_are_unavailable() -> None:
    assert _action(_state("off"), UNAVAILABLE, UNAVAILABLE) == HVACAction.OFF


def test_one_available_relay_is_enough_to_call_it_idle() -> None:
    assert _action(_state("heat"), UNAVAILABLE, OFF) == HVACAction.IDLE


def test_an_unconfigured_relay_is_ignored_even_if_its_state_is_passed() -> None:
    assert _action(_state("heat"), OFF, ON, has_cooling=False) == HVACAction.IDLE


@pytest.mark.parametrize(
    ("thermostat", "expected"),
    [
        (_state("heat", hvac_action="heating"), HVACAction.HEATING),
        (_state("cool", hvac_action="cooling"), HVACAction.COOLING),
        (_state("heat", hvac_action="idle"), HVACAction.IDLE),
        (_state("heat"), None),  # the thermostat reports no hvac_action
        (_state("heat", hvac_action="not-an-action"), None),
        (_state("unavailable", hvac_action="heating"), None),
        (None, None),
    ],
)
def test_without_relays_the_thermostats_own_action_is_mirrored(thermostat, expected) -> None:
    assert _action(thermostat, None, None, has_heating=False, has_cooling=False) == expected


# ---------------------------------------------------------------------------
# climate.py — the read-only chart entity
# ---------------------------------------------------------------------------


def test_climate_entity_identity() -> None:
    entity = _climate()

    assert entity._attr_unique_id == "hist1_history"
    assert entity._attr_device_info["identifiers"] == {("climate_guard_switch", "hist1")}
    assert entity._attr_name is None  # takes the device's name
    assert entity._attr_has_entity_name is True
    assert entity._attr_should_poll is False


def test_climate_entity_advertises_no_features_so_it_has_no_controls() -> None:
    entity = _climate()

    assert entity._attr_supported_features == ClimateEntityFeature(0)
    assert not entity._attr_supported_features


def test_current_temperature_follows_the_sensor() -> None:
    hass = _hass()
    hass.states.set(TEMPERATURE, "41.2", {"unit_of_measurement": "°C"})

    assert _climate(hass).current_temperature == 41.2


def test_current_temperature_is_converted_into_the_system_unit() -> None:
    hass = _hass("°F")
    hass.states.set(TEMPERATURE, "21", {"unit_of_measurement": "°C"})
    entity = _climate(hass)

    assert entity.temperature_unit == "°F"
    assert entity.current_temperature == pytest.approx(69.8)


def test_current_temperature_is_none_while_the_sensor_is_unavailable() -> None:
    hass = _hass()
    hass.states.set(TEMPERATURE, "unavailable")

    assert _climate(hass).current_temperature is None


def test_mode_follows_the_thermostat_and_only_that_mode_is_offered() -> None:
    hass = _hass()
    hass.states.set(THERMOSTAT, "heat")
    entity = _climate(hass)

    assert entity.hvac_mode == HVACMode.HEAT
    assert entity.hvac_modes == [HVACMode.HEAT]  # anything else is rejected by Home Assistant


@pytest.mark.parametrize("thermostat_state", ["unavailable", "unknown", "not-a-mode", None])
def test_no_mode_and_no_modes_while_the_thermostat_is_unusable(thermostat_state) -> None:
    hass = _hass()
    if thermostat_state is not None:
        hass.states.set(THERMOSTAT, thermostat_state)
    entity = _climate(hass)

    assert entity.hvac_mode is None
    assert entity.hvac_modes == []


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        ({CONF_TEMPERATURE_SENSOR: TEMPERATURE, CONF_HEATING_ENTITY: HEATING, CONF_COOLING_ENTITY: COOLING}, HVACMode.HEAT_COOL),
        ({CONF_TEMPERATURE_SENSOR: TEMPERATURE, CONF_HEATING_ENTITY: HEATING}, HVACMode.HEAT),
        ({CONF_TEMPERATURE_SENSOR: TEMPERATURE, CONF_COOLING_ENTITY: COOLING}, HVACMode.COOL),
        ({CONF_TEMPERATURE_SENSOR: TEMPERATURE}, HVACMode.OFF),
    ],
)
def test_without_a_thermostat_the_mode_comes_from_the_configured_relays(config, expected) -> None:
    entity = _climate(config=config)

    assert entity.hvac_mode == expected
    assert entity.hvac_modes == [expected]


def test_hvac_action_reflects_the_real_relays_not_the_thermostats_request() -> None:
    hass = _hass()
    hass.states.set(THERMOSTAT, "cool", {"hvac_action": "cooling"})
    hass.states.set(HEATING, "on")
    hass.states.set(COOLING, "off")

    assert _climate(hass).hvac_action == HVACAction.HEATING


def test_the_target_is_published_through_extra_state_attributes() -> None:
    hass = _hass()
    hass.states.set(
        THERMOSTAT,
        "heat",
        {"temperature": 55.0, "current_temperature": 40.0, "hvac_action": "heating"},
    )

    # Only the target keys are copied: current_temperature/hvac_action are the entity's own.
    assert _climate(hass).extra_state_attributes == {"temperature": 55.0}


def test_dial_range_is_the_thermostats_own() -> None:
    hass = _hass()
    hass.states.set(THERMOSTAT, "heat", {"min_temp": 40.0, "max_temp": 70.0})
    hass.states.set(TEMPERATURE, "45", {"unit_of_measurement": "°C"})
    entity = _climate(hass)

    assert (entity.min_temp, entity.max_temp) == (40.0, 70.0)


def test_dial_range_falls_back_to_the_entity_defaults_without_a_usable_thermostat() -> None:
    hass = _hass()
    hass.states.set(THERMOSTAT, "unavailable", {"min_temp": 40.0, "max_temp": 70.0})

    unusable = _climate(hass)
    assert (unusable.min_temp, unusable.max_temp) == (7.0, 35.0)
    no_thermostat = _climate(hass, {CONF_TEMPERATURE_SENSOR: TEMPERATURE})
    assert (no_thermostat.min_temp, no_thermostat.max_temp) == (7.0, 35.0)


def test_dial_range_widens_so_a_hot_reading_is_never_off_the_dial() -> None:
    """A 41 °C water temperature must not be clamped to the default 35 °C maximum."""
    hass = _hass()
    hass.states.set(TEMPERATURE, "41.2", {"unit_of_measurement": "°C"})
    no_thermostat = _climate(hass, {CONF_TEMPERATURE_SENSOR: TEMPERATURE})

    assert no_thermostat.max_temp == 42  # rounded up to include 41.2
    assert no_thermostat.min_temp == 7.0  # nothing to widen downwards


def test_dial_range_widens_beyond_the_thermostats_range_in_both_directions() -> None:
    hass = _hass()
    hass.states.set(THERMOSTAT, "heat", {"min_temp": 40.0, "max_temp": 50.0})
    entity = _climate(hass)

    hass.states.set(TEMPERATURE, "52.3", {"unit_of_measurement": "°C"})
    assert (entity.min_temp, entity.max_temp) == (40.0, 53)
    hass.states.set(TEMPERATURE, "38.5", {"unit_of_measurement": "°C"})
    assert (entity.min_temp, entity.max_temp) == (38, 50.0)


def test_dial_range_is_not_widened_while_the_sensor_is_unavailable() -> None:
    hass = _hass()
    hass.states.set(THERMOSTAT, "heat", {"min_temp": 40.0, "max_temp": 70.0})
    hass.states.set(TEMPERATURE, "unavailable")

    entity = _climate(hass)

    assert (entity.min_temp, entity.max_temp) == (40.0, 70.0)


def test_a_target_range_is_passed_through_without_a_none_single_target() -> None:
    hass = _hass()
    hass.states.set(
        THERMOSTAT,
        "heat_cool",
        {"temperature": None, "target_temp_low": 20.0, "target_temp_high": 24.5},
    )

    assert _climate(hass).extra_state_attributes == {
        "target_temp_low": 20.0,
        "target_temp_high": 24.5,
    }


def test_no_extra_attributes_without_a_thermostat_or_while_it_is_unavailable() -> None:
    hass = _hass()
    hass.states.set(THERMOSTAT, "unavailable", {"temperature": 55.0})

    assert _climate(hass).extra_state_attributes is None
    assert _climate(config={CONF_TEMPERATURE_SENSOR: TEMPERATURE}).extra_state_attributes is None


async def test_setting_a_mode_changes_nothing_and_calls_no_service() -> None:
    hass = _hass()
    hass.states.set(THERMOSTAT, "heat")
    hass.states.set(HEATING, "off")
    entity = _climate(hass)
    before = (entity.hvac_mode, entity.hvac_modes, entity.hvac_action)

    await entity.async_set_hvac_mode(HVACMode.OFF)

    assert (entity.hvac_mode, entity.hvac_modes, entity.hvac_action) == before
    hass.services.async_call.assert_not_called()
    assert entity.state_writes == 0


async def test_added_to_hass_follows_every_configured_input() -> None:
    entity = _climate()

    with patch("custom_components.climate_guard_switch.climate.async_track_state_change_event") as track:
        await entity.async_added_to_hass()

    track.assert_called_once_with(
        entity.hass,
        [TEMPERATURE, THERMOSTAT, HEATING, COOLING],
        entity._handle_source_change,
    )
    assert entity.removers == [track.return_value]  # unsubscribed when the entity is removed


async def test_cleared_inputs_are_not_followed() -> None:
    entity = HistoryClimate(_entry(**{CONF_HEATING_ENTITY: None, CONF_COOLING_ENTITY: None}))
    entity.hass = _hass()

    with patch("custom_components.climate_guard_switch.climate.async_track_state_change_event") as track:
        await entity.async_added_to_hass()

    assert track.call_args.args[1] == [TEMPERATURE, THERMOSTAT]


def test_a_source_change_rewrites_the_climate_state() -> None:
    entity = _climate()

    entity._handle_source_change(MagicMock())

    assert entity.state_writes == 1


async def test_climate_platform_adds_a_single_history_climate() -> None:
    add = MagicMock()

    await climate_platform.async_setup_entry(_hass(), _entry(), add)

    (added,), _ = add.call_args
    assert len(added) == 1
    assert isinstance(added[0], HistoryClimate)


# ---------------------------------------------------------------------------
# sensor.py — the long-range statistics sensors
# ---------------------------------------------------------------------------


def _sensor(cls, entry_config: dict | None = None, *args, hass: _HomeAssistant | None = None):
    sensor = cls(_entry(entry_config), *args)
    sensor.hass = hass or _hass()
    return sensor


def test_one_sensor_is_created_per_configured_optional_input() -> None:
    sensors = _history_sensors(_entry())

    assert [type(s) for s in sensors] == [
        HistoryTargetTemperatureSensor,
        HistoryActivitySensor,
        HistoryActivitySensor,
    ]
    assert [s._attr_unique_id for s in sensors] == [
        "hist1_target_temperature",
        "hist1_heating",
        "hist1_cooling",
    ]
    assert [s._attr_translation_key for s in sensors] == [
        "target_temperature",
        "heating",
        "cooling",
    ]


def test_no_temperature_mirror_and_no_sensors_for_unconfigured_inputs() -> None:
    # The source temperature sensor already has its own long-term statistics.
    assert _history_sensors(_entry({CONF_TEMPERATURE_SENSOR: TEMPERATURE})) == []
    only_heating = _history_sensors(_entry({CONF_TEMPERATURE_SENSOR: TEMPERATURE, CONF_HEATING_ENTITY: HEATING}))
    assert [s._attr_unique_id for s in only_heating] == ["hist1_heating"]


def test_an_input_cleared_in_options_no_longer_gets_a_sensor() -> None:
    sensors = _history_sensors(_entry(**{CONF_COOLING_ENTITY: None}))

    assert [s._attr_unique_id for s in sensors] == ["hist1_target_temperature", "hist1_heating"]


def test_every_history_sensor_is_a_measurement_so_it_gets_long_term_statistics() -> None:
    for sensor in _history_sensors(_entry()):
        assert sensor._attr_state_class == "measurement"
        assert sensor._attr_has_entity_name is True
        assert sensor._attr_should_poll is False
        assert sensor._attr_device_info["identifiers"] == {("climate_guard_switch", "hist1")}


def test_target_temperature_sensor_reads_the_thermostats_target() -> None:
    hass = _hass()
    hass.states.set(THERMOSTAT, "heat", {"temperature": 55.0})
    sensor = _sensor(HistoryTargetTemperatureSensor, None, THERMOSTAT, hass=hass)

    assert sensor.native_value == 55.0
    assert sensor.available is True
    assert sensor._attr_device_class == "temperature"


@pytest.mark.parametrize("unit", ["°C", "°F"])
def test_target_temperature_sensor_uses_the_system_unit(unit) -> None:
    sensor = _sensor(HistoryTargetTemperatureSensor, None, THERMOSTAT, hass=_hass(unit))

    assert sensor.native_unit_of_measurement == unit


def test_target_temperature_sensor_has_no_value_in_range_mode() -> None:
    hass = _hass()
    hass.states.set(THERMOSTAT, "heat_cool", {"temperature": None, "target_temp_low": 20.0})
    sensor = _sensor(HistoryTargetTemperatureSensor, None, THERMOSTAT, hass=hass)

    assert sensor.native_value is None


@pytest.mark.parametrize("state", ["unavailable", "unknown", None])
def test_history_sensors_are_unavailable_while_their_source_is(state) -> None:
    hass = _hass()
    if state is not None:
        hass.states.set(THERMOSTAT, state, {"temperature": 55.0})
        hass.states.set(HEATING, state)
    target = _sensor(HistoryTargetTemperatureSensor, None, THERMOSTAT, hass=hass)
    heating = _sensor(HistoryActivitySensor, None, HEATING, "heating", hass=hass)

    assert target.available is False
    assert heating.available is False


def test_activity_sensor_is_100_while_on_and_0_otherwise() -> None:
    hass = _hass()
    heating = _sensor(HistoryActivitySensor, None, HEATING, "heating", hass=hass)

    hass.states.set(HEATING, "on")
    assert heating.native_value == 100
    assert heating.available is True

    hass.states.set(HEATING, "off")
    assert heating.native_value == 0


def test_activity_sensor_unit_and_icons() -> None:
    heating = _sensor(HistoryActivitySensor, None, HEATING, "heating")
    cooling = _sensor(HistoryActivitySensor, None, COOLING, "cooling")

    assert heating._attr_native_unit_of_measurement == "%"
    assert heating._attr_icon == "mdi:fire"
    assert cooling._attr_icon == "mdi:snowflake"


async def test_sensor_follows_only_its_own_source_and_rewrites_on_change() -> None:
    sensor = _sensor(HistoryActivitySensor, None, HEATING, "heating")

    with patch("custom_components.climate_guard_switch.sensor.async_track_state_change_event") as track:
        await sensor.async_added_to_hass()

    track.assert_called_once_with(sensor.hass, [HEATING], sensor._handle_source_change)
    assert sensor.removers == [track.return_value]

    sensor._handle_source_change(MagicMock())
    assert sensor.state_writes == 1


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

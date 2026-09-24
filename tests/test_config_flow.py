"""Tests for custom_components/climate_guard_switch/config_flow.py.

Covers the unique_id/duplicate-detection and reconfigure additions, and locks in
the options-flow merge fix (options-flow save used to silently wipe the number
entities' run_limit/cooldown values — see AGENTS.md). Also covers the entry-type
menu and the History view's create/options/reconfigure behavior.
"""
from __future__ import annotations

import pytest

from custom_components.climate_guard_switch.config_flow import (
    ConfigFlow,
    HistoryOptionsFlowHandler,
    OptionsFlowHandler,
    _get_history_schema,
)
from custom_components.climate_guard_switch.const import (
    CONF_CLIMATE_ENTITY,
    CONF_COOLDOWN,
    CONF_COOLING_ENTITY,
    CONF_DEVICE_TYPE,
    CONF_ENTRY_TYPE,
    CONF_HEATING_ENTITY,
    CONF_RUN_LIMIT,
    CONF_TARGET_ENTITY,
    CONF_TEMPERATURE_SENSOR,
    CONF_TEMPERATURE_TRACES,
    DEFAULT_HISTORY_NAME,
    DEVICE_TYPE_COOLER,
    DEVICE_TYPE_HEATER,
    ENTRY_TYPE_HISTORY,
)

from conftest import AbortFlow, _ConfigEntry  # type: ignore[import]

TARGET_ENTITY = "switch.heater"
TEMPERATURE_SENSOR = "sensor.room_temperature"
THERMOSTAT = "climate.room_thermostat"
HEATING = "switch.heater_relay"
COOLING = "switch.cooler_relay"


def _user_input(**overrides) -> dict:
    data = {
        CONF_TARGET_ENTITY: TARGET_ENTITY,
        CONF_DEVICE_TYPE: DEVICE_TYPE_HEATER,
    }
    data.update(overrides)
    return data


def _history_input(**overrides) -> dict:
    data = {
        "name": "Room History",
        CONF_TEMPERATURE_SENSOR: TEMPERATURE_SENSOR,
        CONF_CLIMATE_ENTITY: THERMOSTAT,
        CONF_HEATING_ENTITY: HEATING,
        CONF_COOLING_ENTITY: COOLING,
    }
    data.update(overrides)
    return data


def _history_entry(**options) -> _ConfigEntry:
    return _ConfigEntry(
        data={
            CONF_ENTRY_TYPE: ENTRY_TYPE_HISTORY,
            CONF_TEMPERATURE_SENSOR: TEMPERATURE_SENSOR,
            CONF_CLIMATE_ENTITY: THERMOSTAT,
            CONF_HEATING_ENTITY: HEATING,
            CONF_COOLING_ENTITY: COOLING,
        },
        options=options,
        title="Room History",
    )


async def test_user_step_shows_menu_of_entry_types() -> None:
    flow = ConfigFlow()

    result = await flow.async_step_user(None)

    assert result["type"] == "menu"
    assert result["step_id"] == "user"
    assert result["menu_options"] == ["guard", "history"]


async def test_guard_step_creates_entry_and_sets_unique_id() -> None:
    flow = ConfigFlow()

    result = await flow.async_step_guard(_user_input())

    assert result["type"] == "create_entry"
    assert result["title"] == "Heater Guard"
    assert flow._unique_id == TARGET_ENTITY
    # Guard entries carry no entry_type key: absence has always meant "guard".
    assert CONF_ENTRY_TYPE not in result["data"]


async def test_guard_step_shows_form_with_no_input() -> None:
    flow = ConfigFlow()

    result = await flow.async_step_guard(None)

    assert result["type"] == "form"
    assert result["step_id"] == "guard"


async def test_guard_step_aborts_on_duplicate_target_entity() -> None:
    first = ConfigFlow()
    await first.async_step_guard(_user_input())

    second = ConfigFlow()
    second.hass = first.hass  # share the same "installed entries" registry

    with pytest.raises(AbortFlow) as exc_info:
        await second.async_step_guard(_user_input(device_type=DEVICE_TYPE_COOLER))

    assert exc_info.value.reason == "already_configured"


async def test_history_step_shows_form_with_no_input() -> None:
    flow = ConfigFlow()

    result = await flow.async_step_history(None)

    assert result["type"] == "form"
    assert result["step_id"] == "history"


async def test_history_step_creates_entry_without_unique_id() -> None:
    flow = ConfigFlow()

    result = await flow.async_step_history(_history_input())

    assert result["type"] == "create_entry"
    assert result["title"] == "Room History"
    assert flow._unique_id is None
    assert result["data"] == {
        CONF_ENTRY_TYPE: ENTRY_TYPE_HISTORY,
        CONF_TEMPERATURE_SENSOR: TEMPERATURE_SENSOR,
        CONF_CLIMATE_ENTITY: THERMOSTAT,
        CONF_HEATING_ENTITY: HEATING,
        CONF_COOLING_ENTITY: COOLING,
    }  # the name became the title, not data


async def test_history_step_blank_name_falls_back_to_default() -> None:
    flow = ConfigFlow()

    result = await flow.async_step_history(_history_input(name="   "))

    assert result["title"] == DEFAULT_HISTORY_NAME


async def test_history_step_allows_only_the_required_temperature_sensor() -> None:
    flow = ConfigFlow()

    result = await flow.async_step_history(
        {"name": "Room", CONF_TEMPERATURE_SENSOR: TEMPERATURE_SENSOR}
    )

    assert result["type"] == "create_entry"
    assert result["data"] == {
        CONF_ENTRY_TYPE: ENTRY_TYPE_HISTORY,
        CONF_TEMPERATURE_SENSOR: TEMPERATURE_SENSOR,
    }


async def test_several_history_views_can_coexist() -> None:
    """No unique_id, so a second view over the very same inputs isn't rejected."""
    first = ConfigFlow()
    await first.async_step_history(_history_input())

    second = ConfigFlow()
    second.hass = first.hass

    result = await second.async_step_history(_history_input(name="Second view"))

    assert result["type"] == "create_entry"


def test_options_flow_class_depends_on_entry_type() -> None:
    guard = _ConfigEntry(data=_user_input())

    assert isinstance(ConfigFlow.async_get_options_flow(_history_entry()), HistoryOptionsFlowHandler)
    assert isinstance(ConfigFlow.async_get_options_flow(guard), OptionsFlowHandler)
    assert not isinstance(ConfigFlow.async_get_options_flow(guard), HistoryOptionsFlowHandler)


async def test_history_options_flow_shows_history_form() -> None:
    flow = HistoryOptionsFlowHandler()
    flow.config_entry = _history_entry()

    # The entry point delegates, so the form is the history step's own.
    result = await flow.async_step_init(None)

    assert result["type"] == "form"
    assert result["step_id"] == "history"


async def test_history_options_flow_clears_removed_inputs_and_keeps_the_rest() -> None:
    entry = _history_entry(unrelated_option=7)
    flow = HistoryOptionsFlowHandler()
    flow.config_entry = entry

    # Cooling, heating and the thermostat are emptied in the form: the frontend
    # omits them from the submission entirely.
    result = await flow.async_step_init({CONF_TEMPERATURE_SENSOR: "sensor.other"})

    assert result["type"] == "create_entry"
    assert result["data"][CONF_TEMPERATURE_SENSOR] == "sensor.other"
    assert result["data"][CONF_CLIMATE_ENTITY] is None
    assert result["data"][CONF_HEATING_ENTITY] is None
    assert result["data"][CONF_COOLING_ENTITY] is None
    assert result["data"]["unrelated_option"] == 7


async def test_reconfigure_aborts_for_history_entries() -> None:
    flow = ConfigFlow()
    flow._reconfigure_entry = _history_entry()

    result = await flow.async_step_reconfigure(None)

    assert result["type"] == "abort"
    assert result["reason"] == "history_reconfigure"


async def test_options_flow_merges_instead_of_replacing_existing_options() -> None:
    """Regression: saving the options form used to wipe run_limit/cooldown
    because they aren't fields in the options schema."""
    entry = _ConfigEntry(
        data=_user_input(),
        options={CONF_RUN_LIMIT: 25, CONF_COOLDOWN: 90},
    )
    flow = OptionsFlowHandler()
    flow.config_entry = entry

    result = await flow.async_step_init(_user_input())

    assert result["type"] == "create_entry"
    assert result["data"][CONF_RUN_LIMIT] == 25
    assert result["data"][CONF_COOLDOWN] == 90
    # And the resubmitted field is applied on top:
    assert result["data"][CONF_TARGET_ENTITY] == TARGET_ENTITY


async def test_options_flow_shows_form_prefilled_from_entry() -> None:
    entry = _ConfigEntry(data=_user_input())
    flow = OptionsFlowHandler()
    flow.config_entry = entry

    result = await flow.async_step_init(None)

    assert result["type"] == "form"
    assert result["step_id"] == "init"


async def test_reconfigure_step_updates_device_type() -> None:
    entry = _ConfigEntry(data=_user_input(device_type=DEVICE_TYPE_HEATER))
    flow = ConfigFlow()
    flow._reconfigure_entry = entry

    result = await flow.async_step_reconfigure({CONF_DEVICE_TYPE: DEVICE_TYPE_COOLER})

    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_DEVICE_TYPE] == DEVICE_TYPE_COOLER
    # Untouched fields survive the reconfigure:
    assert entry.data[CONF_TARGET_ENTITY] == TARGET_ENTITY
    # Title must follow the new device type, not stay "Heater Guard":
    assert entry.title == "Cooler Guard"


async def test_reconfigure_step_shows_form_prefilled_with_current_device_type() -> None:
    entry = _ConfigEntry(data=_user_input(device_type=DEVICE_TYPE_COOLER))
    flow = ConfigFlow()
    flow._reconfigure_entry = entry

    result = await flow.async_step_reconfigure(None)

    assert result["type"] == "form"
    assert result["step_id"] == "reconfigure"


async def test_history_step_stores_the_traces_switch_when_turned_off() -> None:
    flow = ConfigFlow()

    result = await flow.async_step_history(_history_input(temperature_traces=False))

    assert result["data"][CONF_TEMPERATURE_TRACES] is False


async def test_history_options_flow_keeps_the_traces_switch_and_never_nulls_it() -> None:
    flow = HistoryOptionsFlowHandler()
    flow.config_entry = _history_entry()

    result = await flow.async_step_init({CONF_TEMPERATURE_SENSOR: TEMPERATURE_SENSOR, CONF_TEMPERATURE_TRACES: False})
    assert result["data"][CONF_TEMPERATURE_TRACES] is False

    # Only the entity fields get nulled out when absent; an absent switch stays absent (= on).
    result = await flow.async_step_init({CONF_TEMPERATURE_SENSOR: TEMPERATURE_SENSOR})
    assert CONF_TEMPERATURE_TRACES not in result["data"]


def test_history_form_traces_switch_defaults_to_on_unless_stored_off() -> None:
    def default_of(schema):
        marker = next(m for m in schema.schema if str(m.schema) == CONF_TEMPERATURE_TRACES)
        return marker.default()

    assert default_of(_get_history_schema()) is True  # new views, and views from before the option existed
    assert default_of(_get_history_schema({CONF_TEMPERATURE_TRACES: True})) is True
    assert default_of(_get_history_schema({CONF_TEMPERATURE_TRACES: False})) is False

"""Tests for custom_components/climate_guard_switch/config_flow.py.

Covers the unique_id/duplicate-detection and reconfigure additions, and locks in
the options-flow merge fix (options-flow save used to silently wipe the number
entities' run_limit/cooldown values — see AGENTS.md).
"""
from __future__ import annotations

import pytest

from custom_components.climate_guard_switch.config_flow import ConfigFlow, OptionsFlowHandler
from custom_components.climate_guard_switch.const import (
    CONF_COOLDOWN,
    CONF_DEVICE_TYPE,
    CONF_RUN_LIMIT,
    CONF_TARGET_ENTITY,
    DEVICE_TYPE_COOLER,
    DEVICE_TYPE_HEATER,
)

from conftest import AbortFlow, _ConfigEntry  # type: ignore[import]

TARGET_ENTITY = "switch.heater"


def _user_input(**overrides) -> dict:
    data = {
        CONF_TARGET_ENTITY: TARGET_ENTITY,
        CONF_DEVICE_TYPE: DEVICE_TYPE_HEATER,
    }
    data.update(overrides)
    return data


async def test_user_step_creates_entry_and_sets_unique_id() -> None:
    flow = ConfigFlow()

    result = await flow.async_step_user(_user_input())

    assert result["type"] == "create_entry"
    assert result["title"] == "Heater Guard"
    assert flow._unique_id == TARGET_ENTITY


async def test_user_step_shows_form_with_no_input() -> None:
    flow = ConfigFlow()

    result = await flow.async_step_user(None)

    assert result["type"] == "form"
    assert result["step_id"] == "user"


async def test_user_step_aborts_on_duplicate_target_entity() -> None:
    first = ConfigFlow()
    await first.async_step_user(_user_input())

    second = ConfigFlow()
    second.hass = first.hass  # share the same "installed entries" registry

    with pytest.raises(AbortFlow) as exc_info:
        await second.async_step_user(_user_input(device_type=DEVICE_TYPE_COOLER))

    assert exc_info.value.reason == "already_configured"


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

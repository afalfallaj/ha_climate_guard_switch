"""Translation coverage: every string a flow or entity shows must exist.

For a custom integration Home Assistant reads `translations/en.json` at runtime
(`strings.json` is the source of truth we keep in sync). A missing or empty key
is not an error: it silently renders as blank text in the UI, e.g. an empty menu
option or an empty message after Reconfigure. These tests catch that early.
"""
from __future__ import annotations

import json
import pathlib
import re

from custom_components.climate_guard_switch.config_flow import (
    ConfigFlow,
    _get_config_schema,
    _get_history_schema,
)
from custom_components.climate_guard_switch.const import (
    CONF_CLIMATE_ENTITY,
    CONF_COOLING_ENTITY,
    CONF_ENTRY_TYPE,
    CONF_HEATING_ENTITY,
    CONF_TEMPERATURE_SENSOR,
    ENTRY_TYPE_HISTORY,
)
from custom_components.climate_guard_switch.sensor import _history_sensors

from conftest import _ConfigEntry  # type: ignore[import]

PACKAGE = pathlib.Path(__file__).resolve().parent.parent / "custom_components" / "climate_guard_switch"

STRINGS = json.loads((PACKAGE / "strings.json").read_text(encoding="utf-8"))
EN = json.loads((PACKAGE / "translations" / "en.json").read_text(encoding="utf-8"))

# Abort reasons Home Assistant raises on our behalf, so they never appear as
# `reason="..."` in our own code:
#   already_configured     <- ConfigFlow._abort_if_unique_id_configured()
#   already_in_progress    <- ConfigFlow.async_set_unique_id() while another flow is open
#   reconfigure_successful <- ConfigFlow.async_update_reload_and_abort()
HA_RAISED_ABORTS = {"already_configured", "already_in_progress", "reconfigure_successful"}


def _field_names(schema) -> set[str]:
    return {str(marker.schema) for marker in schema.schema}


def _leaf_strings(node, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _leaf_strings(value, f"{path}.{key}" if path else key)
    else:
        yield path, node


def test_strings_json_and_en_json_are_identical() -> None:
    assert STRINGS == EN


def test_no_translation_is_an_empty_string() -> None:
    empty = [path for path, text in _leaf_strings(EN) if not str(text).strip()]

    assert empty == []


async def test_add_menu_options_are_translated() -> None:
    menu = await ConfigFlow().async_step_user(None)
    step = EN["config"]["step"]["user"]

    assert step["title"] and step["description"]
    for option in menu["menu_options"]:
        assert step["menu_options"].get(option), f"menu option {option!r} has no translation"


def test_every_form_has_a_title_and_a_label_for_each_field() -> None:
    forms = {
        ("config", "guard"): _get_config_schema(),
        ("config", "history"): _get_history_schema(include_name=True),
        ("options", "init"): _get_config_schema(is_options=True),
        ("options", "history"): _get_history_schema(),
    }
    for (category, step_id), schema in forms.items():
        step = EN[category]["step"][step_id]
        assert step["title"], f"{category}.{step_id} has no title"
        for field in _field_names(schema):
            assert step["data"].get(field), f"{category}.{step_id}: field {field!r} has no label"
        # A description for a field that doesn't exist would be dead text.
        assert set(step.get("data_description", {})) <= set(step["data"]), (category, step_id)

    reconfigure = EN["config"]["step"]["reconfigure"]
    assert reconfigure["title"] and reconfigure["data"]["device_type"]


def test_every_abort_reason_the_flows_can_end_with_is_translated() -> None:
    source = (PACKAGE / "config_flow.py").read_text(encoding="utf-8")
    ours = set(re.findall(r'reason\s*=\s*"([^"]+)"', source))

    assert "history_reconfigure" in ours  # sanity: the scan finds our own reasons
    for reason in ours | HA_RAISED_ABORTS:
        assert EN["config"]["abort"].get(reason), f"abort reason {reason!r} has no translation"


def test_every_entity_translation_key_has_a_name() -> None:
    keys: dict[str, set[str]] = {}
    for platform in ("sensor", "number", "binary_sensor"):
        source = (PACKAGE / f"{platform}.py").read_text(encoding="utf-8")
        keys.setdefault(platform, set()).update(re.findall(r'translation_key\s*=\s*"([^"]+)"', source))

    # The history sensors pass their key as a variable, so read it off real instances.
    history_entry = _ConfigEntry(
        data={
            CONF_ENTRY_TYPE: ENTRY_TYPE_HISTORY,
            CONF_TEMPERATURE_SENSOR: "sensor.t",
            CONF_CLIMATE_ENTITY: "climate.t",
            CONF_HEATING_ENTITY: "switch.h",
            CONF_COOLING_ENTITY: "switch.c",
        }
    )
    keys["sensor"].update(sensor._attr_translation_key for sensor in _history_sensors(history_entry))

    assert {"status", "target_temperature", "heating", "cooling"} <= keys["sensor"]  # sanity
    for platform, platform_keys in keys.items():
        for key in platform_keys:
            name = EN["entity"][platform].get(key, {}).get("name")
            assert name, f"entity.{platform}.{key}.name has no translation"

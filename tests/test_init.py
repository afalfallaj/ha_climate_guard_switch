"""Tests for custom_components/climate_guard_switch/__init__.py.

Covers the version 1 -> 2 migration that backfills unique_id for entries
created before duplicate-detection existed.
"""
from __future__ import annotations

from custom_components.climate_guard_switch import async_migrate_entry
from custom_components.climate_guard_switch.const import CONF_TARGET_ENTITY

from conftest import _ConfigEntriesRegistry, _ConfigEntry, _HomeAssistant  # type: ignore[import]

TARGET_ENTITY = "switch.heater"


async def test_migrate_entry_backfills_unique_id_and_bumps_version() -> None:
    hass = _HomeAssistant()
    hass.config_entries = _ConfigEntriesRegistry()
    entry = _ConfigEntry(data={CONF_TARGET_ENTITY: TARGET_ENTITY}, version=1, unique_id=None)

    result = await async_migrate_entry(hass, entry)

    assert result is True
    assert entry.unique_id == TARGET_ENTITY
    assert entry.version == 2


async def test_migrate_entry_is_a_noop_for_current_version() -> None:
    hass = _HomeAssistant()
    hass.config_entries = _ConfigEntriesRegistry()
    entry = _ConfigEntry(
        data={CONF_TARGET_ENTITY: TARGET_ENTITY}, version=2, unique_id=TARGET_ENTITY
    )

    result = await async_migrate_entry(hass, entry)

    assert result is True
    assert entry.unique_id == TARGET_ENTITY
    assert entry.version == 2

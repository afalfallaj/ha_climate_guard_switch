"""Tests for custom_components/climate_guard_switch/__init__.py.

Covers the version 1 -> 2 migration that backfills unique_id for entries
created before duplicate-detection existed, the guard setup/unload, and the
rejection of leftover "History view" entries from v0.0.4–v0.0.6.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from custom_components.climate_guard_switch import (
    async_migrate_entry,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.climate_guard_switch.const import (
    CONF_ENTRY_TYPE,
    CONF_TARGET_ENTITY,
    CONF_TEMPERATURE_SENSOR,
    DOMAIN,
    ENTRY_TYPE_HISTORY,
    PLATFORMS,
)

from conftest import ConfigEntryError, _ConfigEntriesRegistry, _ConfigEntry, _HomeAssistant  # type: ignore[import]

TARGET_ENTITY = "switch.heater"


def _hass() -> _HomeAssistant:
    hass = _HomeAssistant()
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=None)
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    return hass


def _guard_entry() -> _ConfigEntry:
    return _ConfigEntry(data={CONF_TARGET_ENTITY: TARGET_ENTITY})


async def test_setup_guard_entry_builds_coordinator_and_forwards_platforms() -> None:
    hass = _hass()
    entry = _guard_entry()

    with patch("custom_components.climate_guard_switch.ClimateGuardCoordinator") as coordinator_cls:
        coordinator_cls.return_value.async_init = AsyncMock()
        assert await async_setup_entry(hass, entry) is True

    coordinator_cls.assert_called_once_with(hass, entry)
    coordinator_cls.return_value.async_init.assert_awaited_once()
    assert entry.runtime_data is coordinator_cls.return_value
    hass.config_entries.async_forward_entry_setups.assert_awaited_once_with(entry, PLATFORMS)


async def test_unload_guard_entry_unloads_platforms() -> None:
    hass = _hass()
    entry = _guard_entry()

    assert await async_unload_entry(hass, entry) is True

    hass.config_entries.async_unload_platforms.assert_awaited_once_with(entry, PLATFORMS)


async def test_leftover_history_entry_fails_setup_with_a_translated_reason() -> None:
    """A "History view" entry (v0.0.4–v0.0.6) has no target switch; its sensors now
    live on the guard device. It must fail cleanly, with the message to delete it,
    instead of crashing on the missing target entity."""
    hass = _hass()
    entry = _ConfigEntry(data={CONF_ENTRY_TYPE: ENTRY_TYPE_HISTORY, CONF_TEMPERATURE_SENSOR: "sensor.t"})

    with patch("custom_components.climate_guard_switch.ClimateGuardCoordinator") as coordinator_cls:
        with pytest.raises(ConfigEntryError) as exc_info:
            await async_setup_entry(hass, entry)

    assert exc_info.value.translation_domain == DOMAIN
    assert exc_info.value.translation_key == "history_view_removed"
    coordinator_cls.assert_not_called()
    hass.config_entries.async_forward_entry_setups.assert_not_awaited()


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

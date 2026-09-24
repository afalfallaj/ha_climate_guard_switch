"""Tests for custom_components/climate_guard_switch/__init__.py.

Covers the version 1 -> 2 migration that backfills unique_id for entries
created before duplicate-detection existed, and the setup/unload split between
guard entries (coordinator + guard platforms) and History view entries (no
coordinator, read-only platforms).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from custom_components.climate_guard_switch import (
    async_migrate_entry,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.climate_guard_switch.const import (
    CONF_ENTRY_TYPE,
    CONF_TARGET_ENTITY,
    CONF_TEMPERATURE_SENSOR,
    ENTRY_TYPE_HISTORY,
    HISTORY_PLATFORMS,
    PLATFORMS,
)

from conftest import _ConfigEntriesRegistry, _ConfigEntry, _HomeAssistant  # type: ignore[import]

TARGET_ENTITY = "switch.heater"


def _hass() -> _HomeAssistant:
    hass = _HomeAssistant()
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=None)
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    return hass


def _history_entry() -> _ConfigEntry:
    # Deliberately has no CONF_TARGET_ENTITY: History views have no target switch.
    return _ConfigEntry(
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_HISTORY, CONF_TEMPERATURE_SENSOR: "sensor.temperature"}
    )


def _guard_entry() -> _ConfigEntry:
    return _ConfigEntry(data={CONF_TARGET_ENTITY: TARGET_ENTITY})


def test_history_platforms_are_read_only_subset_without_the_guard_controls() -> None:
    assert HISTORY_PLATFORMS != PLATFORMS
    assert len(HISTORY_PLATFORMS) == 2  # climate + sensor only: no switch/number/binary_sensor


async def test_setup_history_entry_builds_no_coordinator_and_forwards_history_platforms() -> None:
    hass = _hass()
    entry = _history_entry()

    with patch("custom_components.climate_guard_switch.ClimateGuardCoordinator") as coordinator_cls:
        assert await async_setup_entry(hass, entry) is True

    coordinator_cls.assert_not_called()
    assert entry.runtime_data is None
    hass.config_entries.async_forward_entry_setups.assert_awaited_once_with(entry, HISTORY_PLATFORMS)


async def test_setup_guard_entry_still_builds_coordinator_and_forwards_guard_platforms() -> None:
    """Regression: the guard path must be exactly what it was before History views."""
    hass = _hass()
    entry = _guard_entry()

    with patch("custom_components.climate_guard_switch.ClimateGuardCoordinator") as coordinator_cls:
        coordinator_cls.return_value.async_init = AsyncMock()
        assert await async_setup_entry(hass, entry) is True

    coordinator_cls.assert_called_once_with(hass, entry)
    coordinator_cls.return_value.async_init.assert_awaited_once()
    assert entry.runtime_data is coordinator_cls.return_value
    hass.config_entries.async_forward_entry_setups.assert_awaited_once_with(entry, PLATFORMS)


async def test_unload_history_entry_unloads_history_platforms() -> None:
    hass = _hass()
    entry = _history_entry()

    assert await async_unload_entry(hass, entry) is True

    hass.config_entries.async_unload_platforms.assert_awaited_once_with(entry, HISTORY_PLATFORMS)


async def test_unload_guard_entry_unloads_guard_platforms() -> None:
    hass = _hass()
    entry = _guard_entry()

    assert await async_unload_entry(hass, entry) is True

    hass.config_entries.async_unload_platforms.assert_awaited_once_with(entry, PLATFORMS)


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

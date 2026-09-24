"""The Climate Guard Switch integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .coordinator import ClimateGuardCoordinator
from .const import (
    CONF_TARGET_ENTITY,
    DOMAIN,
    HISTORY_PLATFORMS,
    PLATFORMS,
)
from .history import is_history_entry

_LOGGER = logging.getLogger(__name__)

type GuardSwitchConfigEntry = ConfigEntry[ClimateGuardCoordinator]

# Entities a History view created in v0.0.4 but no longer does: the read-only
# climate entity and the Heating/Cooling % sensors. Without this their registry
# entries would linger as "unavailable" after an update.
_RETIRED_HISTORY_UNIQUE_ID_SUFFIXES = ("_history", "_heating", "_cooling")
# v0.0.5 registered these hidden and diagnostic; they are plain visible sensors now.
_TRACE_UNIQUE_ID_SUFFIXES = ("_temperature_while_heating", "_temperature_while_cooling")


@callback
def _async_tidy_history_registry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Undo what earlier versions left in the entity registry for a History view.

    The registry keeps `hidden_by` and `entity_category` from an entity's first
    registration, so the v0.0.5 traces would stay hidden/diagnostic on their own.
    Only what the integration itself set is cleared, never a user's choice.
    """
    registry = er.async_get(hass)
    retired = {f"{entry.entry_id}{suffix}" for suffix in _RETIRED_HISTORY_UNIQUE_ID_SUFFIXES}
    traces = {f"{entry.entry_id}{suffix}" for suffix in _TRACE_UNIQUE_ID_SUFFIXES}
    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if reg_entry.unique_id in retired:
            registry.async_remove(reg_entry.entity_id)
        elif reg_entry.unique_id in traces:
            updates: dict[str, None] = {}
            if reg_entry.hidden_by is er.RegistryEntryHider.INTEGRATION:
                updates["hidden_by"] = None
            if reg_entry.entity_category is EntityCategory.DIAGNOSTIC:
                updates["entity_category"] = None
            if updates:
                registry.async_update_entity(reg_entry.entity_id, **updates)


async def async_setup_entry(hass: HomeAssistant, entry: GuardSwitchConfigEntry) -> bool:
    """Set up Climate Guard Switch from a config entry."""

    if is_history_entry(entry):
        # A History view is a read-only mirror of other entities: no coordinator,
        # no runtime_data and no target switch, so none of the guard setup applies.
        _async_tidy_history_registry(hass, entry)
        await hass.config_entries.async_forward_entry_setups(entry, HISTORY_PLATFORMS)
        return True

    coordinator = ClimateGuardCoordinator(hass, entry)
    await coordinator.async_init()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if is_history_entry(entry):
        return await hass.config_entries.async_unload_platforms(entry, HISTORY_PLATFORMS)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entry to the current version."""
    if entry.version == 1:
        # Version 1 entries predate unique_id support: one guard per target
        # switch wasn't enforced. Backfill it from existing data so upgraded
        # entries get the same duplicate protection new ones do.
        hass.config_entries.async_update_entry(
            entry,
            unique_id=entry.data[CONF_TARGET_ENTITY],
            version=2,
        )
        _LOGGER.info("Migrated Climate Guard Switch entry %s to version 2", entry.entry_id)

    return True

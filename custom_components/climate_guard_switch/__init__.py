"""The Climate Guard Switch integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import ClimateGuardCoordinator
from .const import (
    CONF_TARGET_ENTITY,
    DOMAIN,
    PLATFORMS,
)

_LOGGER = logging.getLogger(__name__)

type GuardSwitchConfigEntry = ConfigEntry[ClimateGuardCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: GuardSwitchConfigEntry) -> bool:
    """Set up Climate Guard Switch from a config entry."""
    
    coordinator = ClimateGuardCoordinator(hass, entry)
    await coordinator.async_init()
    
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
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

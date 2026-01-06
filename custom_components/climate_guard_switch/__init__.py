"""The Climate Guard Switch integration."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_COOLDOWN,
    CONF_HEARTBEAT,
    CONF_RUN_LIMIT,
    DEFAULT_COOLDOWN,
    DEFAULT_HEARTBEAT,
    DEFAULT_RUN_LIMIT,
    DOMAIN,
)

PLATFORMS: list[Platform] = [Platform.SWITCH, Platform.NUMBER]

@dataclass
class GuardSwitchRuntimeData:
    """Runtime data shared between platforms."""
    run_limit: int
    cooldown: int
    heartbeat_interval: int

type GuardSwitchConfigEntry = ConfigEntry[GuardSwitchRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: GuardSwitchConfigEntry) -> bool:
    """Set up Climate Guard Switch from a config entry."""
    
    # Initialize runtime data from config or defaults
    # Merge data and options (options take precedence)
    config = {**entry.data, **entry.options}
    
    entry.runtime_data = GuardSwitchRuntimeData(
        run_limit=config.get(CONF_RUN_LIMIT, DEFAULT_RUN_LIMIT),
        cooldown=config.get(CONF_COOLDOWN, DEFAULT_COOLDOWN),
        heartbeat_interval=config.get(CONF_HEARTBEAT, DEFAULT_HEARTBEAT),
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_reload_entry(hass: HomeAssistant, entry: GuardSwitchConfigEntry) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

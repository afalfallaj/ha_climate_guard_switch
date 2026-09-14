"""Diagnostics support for Climate Guard Switch."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import GuardSwitchConfigEntry
from .const import CONF_CLIMATE_ENTITY, CONF_SUN_ENTITY, CONF_TARGET_ENTITY, CONF_WEATHER_ENTITY

TO_REDACT = {CONF_TARGET_ENTITY, "unique_id"}

async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: GuardSwitchConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    
    # helper to get state safely
    def _get_state(entity_id: str | None) -> dict[str, Any] | None:
        if not entity_id:
            return None
        if state := hass.states.get(entity_id):
            return state.as_dict()
        return {"state": "unknown", "entity_id": entity_id}

    # Merge config and options to show effective config
    effective_config = {**entry.data, **entry.options}
    config_data = async_redact_data(effective_config, TO_REDACT)

    coordinator = entry.runtime_data
    runtime_data = None
    if coordinator:
        last_run = coordinator.data.get("last_run")
        runtime_data = {
            "guard_enabled": coordinator.data.get("guard_enabled"),
            "target_active": coordinator.data.get("target_active"),
            "status": coordinator.data.get("status"),
            "reason": coordinator.data.get("reason"),
            "cooldown_active": coordinator.data.get("cooldown_active"),
            "last_run": last_run.isoformat() if last_run else None,
            "run_limit_minutes": coordinator.run_limit.total_seconds() / 60,
            "cooldown_minutes": coordinator.cooldown.total_seconds() / 60,
            "heartbeat_interval_seconds": coordinator.heartbeat_interval.total_seconds(),
            "cooldown_enabled": coordinator.data.get("cooldown_enabled"),
            "run_limit_enabled": coordinator.data.get("run_limit_enabled"),
            "run_limit_enforced": coordinator.data.get("run_limit_enforced"),
        }

    # Snapshot of related entities
    related_states = {
        "target": _get_state(effective_config.get(CONF_TARGET_ENTITY)),
        "sun": _get_state(effective_config.get(CONF_SUN_ENTITY)),
        "weather": _get_state(effective_config.get(CONF_WEATHER_ENTITY)),
        "climate": _get_state(effective_config.get(CONF_CLIMATE_ENTITY)),
    }

    return {
        "config": config_data,
        "runtime_limits": runtime_data,
        "related_entities": related_states,
    }

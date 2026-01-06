"""Coordinator for Climate Guard Switch."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components.climate import ATTR_TEMPERATURE
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_ON,
)
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ALLOWED_WEATHER,
    CONF_CLIMATE_ENTITY,
    CONF_COOLDOWN,
    CONF_DEVICE_TYPE,
    CONF_HEARTBEAT,
    CONF_RUN_LIMIT,
    CONF_SUN_ENTITY,
    CONF_TARGET_ENTITY,
    CONF_WEATHER_ENTITY,
    DEFAULT_COOLDOWN,
    DEFAULT_HEARTBEAT,
    DEFAULT_RUN_LIMIT,
    DEVICE_TYPE_HEATER,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class ClimateGuardCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching data from the API."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None, # Driven by events, not polling
        )
        self.config_entry = config_entry
        self._config = {**config_entry.data, **config_entry.options}
        
        # Identity
        self.entry_id = config_entry.entry_id
        self.device_name = config_entry.title

        # Configuration
        self._target_entity = self._config[CONF_TARGET_ENTITY]
        self._device_type = self._config.get(CONF_DEVICE_TYPE, DEVICE_TYPE_HEATER)
        self._sun_entity = self._config.get(CONF_SUN_ENTITY)
        self._weather_entity = self._config.get(CONF_WEATHER_ENTITY)
        self._climate_entity = self._config.get(CONF_CLIMATE_ENTITY)
        self._allowed_weather = self._config.get(CONF_ALLOWED_WEATHER, [])

        # Internal State
        self._guard_enabled = False
        self._target_is_active = False
        self._last_run_time: datetime | None = None
        self._run_start_time: datetime | None = None
        self._heartbeat_remove_listener: Any = None
        self._cooldown_bypass: bool = False
        self._block_reason: str | None = None
        
        # Initial Data
        self.data = {
            "guard_enabled": False,
            "target_active": False,
            "status": "Initializing",
            "reason": None
        }

    async def async_init(self):
        """Perform async initialization (listeners)."""
        # Restore logic handles state restoration in entity, but here we start fresh or need a way to restore.
        # Ideally, the Switch Entity restores the "Guard Enabled" state and tells the coordinator.
        
        # Listen for Trigger Changes (Gates)
        entities_to_watch = []
        if self._sun_entity:
            entities_to_watch.append(self._sun_entity)
        if self._weather_entity:
            entities_to_watch.append(self._weather_entity)
        if self._climate_entity:
            entities_to_watch.append(self._climate_entity)
            
        if entities_to_watch:
            self.config_entry.async_on_unload(
                async_track_state_change_event(
                    self.hass, entities_to_watch, self._on_dependency_change
                )
            )

        # Initial Check
        await self._async_check_and_update()

    def set_guard_state(self, enabled: bool, last_run: datetime | None = None):
        """Set the guard enabled state (called by Switch Entity on restore/toggle)."""
        self._guard_enabled = enabled
        if last_run:
            self._last_run_time = last_run
        
        # Trigger update
        self.hass.async_create_task(self._async_check_and_update())

    @property
    def run_limit(self) -> timedelta:
        """Get run limit from config/options (Runtime)."""
        # We read directly from options to allow runtime updates
        minutes = self.config_entry.options.get(CONF_RUN_LIMIT, self._config.get(CONF_RUN_LIMIT, DEFAULT_RUN_LIMIT))
        return timedelta(minutes=minutes)

    @property
    def cooldown(self) -> timedelta:
        """Get cooldown from config/options (Runtime)."""
        minutes = self.config_entry.options.get(CONF_COOLDOWN, self._config.get(CONF_COOLDOWN, DEFAULT_COOLDOWN))
        return timedelta(minutes=minutes)

    @property
    def heartbeat_interval(self) -> timedelta:
        """Get heartbeat from config/options (Runtime)."""
        seconds = self.config_entry.options.get(CONF_HEARTBEAT, self._config.get(CONF_HEARTBEAT, DEFAULT_HEARTBEAT))
        return timedelta(seconds=seconds)

    @callback
    async def _on_dependency_change(self, event: Event) -> None:
        """Handle state changes in dependencies."""
        entity_id = event.data.get("entity_id")
        
        if entity_id == self._climate_entity:
            old_state = event.data.get("old_state")
            new_state = event.data.get("new_state")
            if old_state and new_state:
                 old_temp = old_state.attributes.get(ATTR_TEMPERATURE)
                 new_temp = new_state.attributes.get(ATTR_TEMPERATURE)
                 if old_temp != new_temp:
                     _LOGGER.info("%s: Climate target changed. Bypassing cooldown.", self.device_name)
                     self._cooldown_bypass = True

        await self._async_check_and_update()

    def _is_cooldown_active(self) -> bool:
        if self.cooldown.total_seconds() == 0:
            return False
            
        if not self._last_run_time:
            return False
        diff = dt_util.now() - self._last_run_time
        return diff < self.cooldown

    def _check_conditions(self) -> tuple[bool, str | None]:
        # 1. Sun Check
        if self._sun_entity:
            sun_state = self.hass.states.get(self._sun_entity)
            if sun_state and sun_state.state != "above_horizon":
                 return False, f"Sun is {sun_state.state}"

        # 2. Weather Check
        if self._weather_entity and self._allowed_weather:
            weather_state = self.hass.states.get(self._weather_entity)
            if not weather_state:
                 return False, "Weather unavailable"
            
            if weather_state.state not in self._allowed_weather:
                 return False, f"Weather is {weather_state.state}"

        # 3. Cooldown Check
        if self._is_cooldown_active():
             if self._cooldown_bypass:
                 _LOGGER.info("%s: Cooldown bypassed by user override.", self.device_name)
             else:
                 remaining = (self._last_run_time + self.cooldown) - dt_util.now()
                 return False, f"Cooldown ({str(remaining).split('.')[0]})"

        return True, None

    async def _async_check_and_update(self):
        """Core Logic Loop."""
        if not self._guard_enabled:
            if self._target_is_active:
                await self._stop_target()
            self._block_reason = "Guard Disabled"
            self._update_data()
            return

        is_allowed, reason = self._check_conditions()
        self._block_reason = reason

        if is_allowed:
            if not self._target_is_active:
                await self._start_target()
            
            if self.heartbeat_interval.total_seconds() > 0:
                 self._ensure_heartbeat_running()
        else:
            if self._target_is_active:
                _LOGGER.info("%s: Conditions no longer met (%s). Stopping.", self.device_name, reason)
                await self._stop_target()

        self._update_data()

    def _update_data(self):
        """Update subscribers."""
        status = "Active (Running)" if self._target_is_active else f"Idle ({self._block_reason or 'Off'})"
        self.async_set_updated_data({
            "guard_enabled": self._guard_enabled,
            "target_active": self._target_is_active,
            "status": status,
            "reason": self._block_reason,
            "cooldown_active": self._is_cooldown_active(),
            "last_run": self._last_run_time,
        })

    async def _start_target(self):
        _LOGGER.info("%s: Starting Target %s", self.device_name, self._target_entity)
        if self._cooldown_bypass:
            self._cooldown_bypass = False
            
        self._target_is_active = True
        self._run_start_time = dt_util.now()
        
        await self._pulse_target_on()
        
        if self.heartbeat_interval.total_seconds() > 0:
             self._ensure_heartbeat_running()

    async def _stop_target(self):
        _LOGGER.info("%s: Stopping Target %s", self.device_name, self._target_entity)
        self._stop_heartbeat()
        
        await self.hass.services.async_call(
            "switch",
            SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: self._target_entity},
            blocking=False,
        )

        self._target_is_active = False
        self._last_run_time = dt_util.now()
        self._run_start_time = None

    def _ensure_heartbeat_running(self):
        if self._heartbeat_remove_listener:
            return

        _LOGGER.debug("%s: Starting heartbeat loop.", self.device_name)
        self._heartbeat_remove_listener = async_track_time_interval(
            self.hass,
            self._heartbeat_tick,
            self.heartbeat_interval,
        )

    def _stop_heartbeat(self):
        if self._heartbeat_remove_listener:
            _LOGGER.debug("%s: Stopping heartbeat loop.", self.device_name)
            self._heartbeat_remove_listener()
            self._heartbeat_remove_listener = None

    async def _heartbeat_tick(self, now: datetime):
        if self._target_is_active and self._run_start_time:
             # Check if run limit is enabled (Use total_seconds to compare with 0)
             if self.run_limit.total_seconds() > 0:
                 if now - self._run_start_time > self.run_limit:
                     _LOGGER.info("%s: Run limit reached. Stopping.", self.device_name)
                     await self._stop_target()
                     return # Loop stopped in _stop_target

        if self._target_is_active:
             await self._pulse_target_on()
        
        await self._async_check_and_update()

    async def _pulse_target_on(self):
        try:
             await self.hass.services.async_call(
                "switch",
                SERVICE_TURN_ON,
                {ATTR_ENTITY_ID: self._target_entity},
                blocking=True,
            )
        except Exception as err:
             _LOGGER.warning("%s: Failed to pulse target: %s", self.device_name, err)

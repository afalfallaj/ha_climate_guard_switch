"""Switch platform for Climate Guard Switch."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.climate import ATTR_TEMPERATURE
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from . import GuardSwitchConfigEntry
from .const import (
    CONF_ALLOWED_WEATHER,
    CONF_CLIMATE_ENTITY,
    CONF_DEVICE_TYPE,
    CONF_SUN_ENTITY,
    CONF_TARGET_ENTITY,
    CONF_WEATHER_ENTITY,
    DEVICE_TYPE_HEATER,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: GuardSwitchConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Climate Guard Switch from a config entry."""
    async_add_entities([ClimateGuardSwitch(hass, config_entry)])


class ClimateGuardSwitch(SwitchEntity, RestoreEntity):
    """Representation of a Climate Guard Switch."""

    def __init__(self, hass: HomeAssistant, config_entry: GuardSwitchConfigEntry) -> None:
        """Initialize the switch."""
        self.hass = hass
        self._config_entry = config_entry
        # Options take precedence over data
        self._config = {**config_entry.data, **config_entry.options}
        self._attr_has_entity_name = True
        self._attr_name = None # Use device name as prefix
        self._attr_unique_id = config_entry.entry_id
        
        # Internal State
        self._guard_enabled = False # This is the state of the Switch Entity (Optimistic)
        self._target_is_active = False # This is the actual state of the Hardware
        
        # Configuration
        self._target_entity = self._config[CONF_TARGET_ENTITY]
        self._device_type = self._config.get(CONF_DEVICE_TYPE, DEVICE_TYPE_HEATER)
        self._sun_entity = self._config.get(CONF_SUN_ENTITY)
        self._weather_entity = self._config.get(CONF_WEATHER_ENTITY)
        self._climate_entity = self._config.get(CONF_CLIMATE_ENTITY)
        self._allowed_weather = self._config.get(CONF_ALLOWED_WEATHER, [])
        
        # State tracking
        self._last_run_time: datetime | None = None
        self._run_start_time: datetime | None = None
        self._heartbeat_remove_listener: Any = None
        self._cooldown_bypass: bool = False
        self._block_reason: str | None = None

        # Device Info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name=config_entry.title,
            manufacturer="Custom",
            model="Climate Guard Switch",
        )

    @property
    def icon(self) -> str | None:
        """Return the icon to use in the frontend."""
        if self._device_type == DEVICE_TYPE_HEATER:
            return "mdi:fire" if self._target_is_active else "mdi:fire-off"
        return "mdi:snowflake" if self._target_is_active else "mdi:snowflake-off"
    
    @property
    def is_on(self) -> bool:
        """Return true if switch is on (Guard Enabled)."""
        return self._guard_enabled

    # Properties that read dynamically from runtime data
    @property
    def _run_limit(self) -> timedelta:
        return timedelta(minutes=self._config_entry.runtime_data.run_limit)

    @property
    def _cooldown(self) -> timedelta:
        return timedelta(minutes=self._config_entry.runtime_data.cooldown)
    
    @property
    def _heartbeat_interval(self) -> timedelta:
        return timedelta(seconds=self._config_entry.runtime_data.heartbeat_interval)

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        
        if last_state:
            # Restore Guard State
            self._guard_enabled = last_state.state == STATE_ON
            
            # Restore run timings
            last_run_ts = last_state.attributes.get("last_run_time")
            if last_run_ts:
                self._last_run_time = dt_util.parse_datetime(last_run_ts)
        else:
            self._guard_enabled = False

        # Listen for Trigger Changes (Gates)
        entities_to_watch = []
        if self._sun_entity:
            entities_to_watch.append(self._sun_entity)
        if self._weather_entity:
            entities_to_watch.append(self._weather_entity)
        if self._climate_entity:
            entities_to_watch.append(self._climate_entity)
            
        if entities_to_watch:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, entities_to_watch, self._on_dependency_change
                )
            )

        # Initial Check
        await self._async_check_and_update()

    @callback
    async def _on_dependency_change(self, event: Event) -> None:
        """Handle state changes in dependencies (Sun, Weather, Climate)."""
        entity_id = event.data.get("entity_id")
        
        # Climate Bypass Logic
        if entity_id == self._climate_entity:
            old_state = event.data.get("old_state")
            new_state = event.data.get("new_state")
            if old_state and new_state:
                 old_temp = old_state.attributes.get(ATTR_TEMPERATURE)
                 new_temp = new_state.attributes.get(ATTR_TEMPERATURE)
                 if old_temp != new_temp:
                     _LOGGER.info("%s: Climate target changed. Bypassing cooldown.", self.name)
                     self._cooldown_bypass = True

        # Re-evaluate logic
        await self._async_check_and_update()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        return {
            "guard_state": "Active (Running)" if self._target_is_active else f"Idle ({self._block_reason or 'Off'})",
            "target_is_active": self._target_is_active,
            "last_run_time": self._last_run_time.isoformat() if self._last_run_time else None,
            "run_start_time": self._run_start_time.isoformat() if self._run_start_time else None,
            "cooldown_active": self._is_cooldown_active(),
            "cooldown_bypass_armed": self._cooldown_bypass,
            "target_entity": self._target_entity,
        }

    def _is_cooldown_active(self) -> bool:
        """Check if cooldown is currently active."""
        if not self._last_run_time:
            return False
        diff = dt_util.now() - self._last_run_time
        return diff < self._cooldown

    def _check_conditions(self) -> tuple[bool, str | None]:
        """Check all gates. Return (IsAllowed, Reason)."""
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
                 _LOGGER.info("%s: Cooldown bypassed by user override.", self.name)
                 # Note: We don't consume ticket here, we consume it when we actually turn ON
             else:
                 remaining = (self._last_run_time + self._cooldown) - dt_util.now()
                 return False, f"Cooldown ({str(remaining).split('.')[0]})"

        return True, None

    async def _async_check_and_update(self):
        """Core Logic Loop: Evaluate Guard + Conditions -> Target."""
        if not self._guard_enabled:
            # Guard Disabled -> Force OFF
            if self._target_is_active:
                await self._stop_target()
            self._block_reason = "Guard Disabled"
            self.async_write_ha_state()
            return

        # Guard Enabled: Check Conditions
        is_allowed, reason = self._check_conditions()
        self._block_reason = reason

        if is_allowed:
            # Safe to Run
            if not self._target_is_active:
                await self._start_target()
            # If already running, ensure heartbeat is active
            if self._heartbeat_interval.total_seconds() > 0:
                 self._ensure_heartbeat_running()
        else:
            # Not Safe to Run
            if self._target_is_active:
                _LOGGER.info("%s: Conditions no longer met (%s). Stopping.", self.name, reason)
                await self._stop_target()

        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the Guard (Arm the system)."""
        _LOGGER.debug("%s: Guard Enabled.", self.name)
        self._guard_enabled = True
        await self._async_check_and_update()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the Guard (Disarm the system)."""
        _LOGGER.debug("%s: Guard Disabled.", self.name)
        self._guard_enabled = False
        await self._async_check_and_update()

    async def _start_target(self):
        """Actually turn on the hardware."""
        _LOGGER.info("%s: Starting Target %s", self.name, self._target_entity)
        if self._cooldown_bypass:
            self._cooldown_bypass = False # Consume ticket
            
        self._target_is_active = True
        self._run_start_time = dt_util.now()
        
        # Initial Pulse
        await self._pulse_target_on()
        
        if self._heartbeat_interval.total_seconds() > 0:
             self._ensure_heartbeat_running()

    async def _stop_target(self):
        """Actually turn off the hardware."""
        _LOGGER.info("%s: Stopping Target %s", self.name, self._target_entity)
        self._stop_heartbeat()
        
        await self.hass.services.async_call(
            "switch",
            SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: self._target_entity},
            blocking=False,
        )

        self._target_is_active = False
        self._last_run_time = dt_util.now() # Mark cooldown start
        self._run_start_time = None

    def _ensure_heartbeat_running(self):
        """Start the heartbeat loop if not running."""
        if self._heartbeat_remove_listener:
            return

        _LOGGER.debug("%s: Starting heartbeat loop.", self.name)
        self._heartbeat_remove_listener = async_track_time_interval(
            self.hass,
            self._heartbeat_tick,
            self._heartbeat_interval,
        )

    def _stop_heartbeat(self):
        """Stop the heartbeat loop."""
        if self._heartbeat_remove_listener:
            _LOGGER.debug("%s: Stopping heartbeat loop.", self.name)
            self._heartbeat_remove_listener()
            self._heartbeat_remove_listener = None

    async def _heartbeat_tick(self, now: datetime):
        """Called periodically by heartbeat timer."""
        # Active Check 1: Run Limit
        if self._target_is_active and self._run_start_time:
             if now - self._run_start_time > self._run_limit:
                 _LOGGER.info("%s: Run limit reached. Stopping.", self.name)
                 await self._stop_target()
                 return # Loop stopped in _stop_target

        # Active Check 2: Pulse
        if self._target_is_active:
             await self._pulse_target_on()
        
        # Periodic Re-evaluation (In case events missed)
        await self._async_check_and_update()

    async def _pulse_target_on(self):
        """Send turn_on command to target entity."""
        try:
             await self.hass.services.async_call(
                "switch",
                SERVICE_TURN_ON,
                {ATTR_ENTITY_ID: self._target_entity},
                blocking=True,
            )
        except Exception as err:
             _LOGGER.warning("%s: Failed to pulse target: %s", self.name, err)

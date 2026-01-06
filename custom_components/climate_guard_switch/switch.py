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
    CONF_HEARTBEAT_ENABLED,
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
        self._config = config_entry.data
        self._attr_has_entity_name = True
        self._attr_name = None # Use device name as prefix
        self._attr_unique_id = config_entry.entry_id
        self._attr_is_on = False
        
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
            return "mdi:fire" if self._attr_is_on else "mdi:fire-off"
        return "mdi:snowflake" if self._attr_is_on else "mdi:snowflake-off"

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
            # Restore last run time from extra attributes if available
            # We will persist it in extra_state_attributes for restoration
            last_run_ts = last_state.attributes.get("last_run_time")
            if last_run_ts:
                self._last_run_time = dt_util.parse_datetime(last_run_ts)

        # Default to OFF on restart for safety
        self._attr_is_on = False

        # Listen for thermostat changes if configured
        if self._climate_entity:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, [self._climate_entity], self._on_climate_change
                )
            )

    @callback
    def _on_climate_change(self, event: Event) -> None:
        """Handle climate state changes."""
        old_state: State | None = event.data.get("old_state")
        new_state: State | None = event.data.get("new_state")

        if not old_state or not new_state:
            return

        # Check if Target Temperature changed
        old_temp = old_state.attributes.get(ATTR_TEMPERATURE)
        new_temp = new_state.attributes.get(ATTR_TEMPERATURE)

        if old_temp != new_temp:
            _LOGGER.info(
                "Climate %s target changed from %s to %s. Bypassing cooldown for next run.",
                self._climate_entity,
                old_temp,
                new_temp,
            )
            self._cooldown_bypass = True

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        return {
            "last_run_time": self._last_run_time.isoformat() if self._last_run_time else None,
            "run_start_time": self._run_start_time.isoformat() if self._run_start_time else None,
            "cooldown_active": self._is_cooldown_active(),
            "cooldown_bypass_armed": self._cooldown_bypass,
            "target_entity": self._target_entity,
            "device_type": self._device_type,
        }

    def _is_cooldown_active(self) -> bool:
        """Check if cooldown is currently active."""
        if not self._last_run_time:
            return False
        diff = dt_util.now() - self._last_run_time
        is_active = diff < self._cooldown
        if is_active:
            _LOGGER.debug(
                "%s: Cooldown active. Last run: %s, Diff: %s, Limit: %s",
                self.name,
                self._last_run_time,
                diff,
                self._cooldown,
            )
        return is_active

    def _check_environment(self) -> bool:
        """Check environmental gates. Return True if safe to run."""
        # 1. Sun Check
        if self._sun_entity:
            sun_state = self.hass.states.get(self._sun_entity)
            if sun_state and sun_state.state != "above_horizon":
                 _LOGGER.warning(
                     "%s: Blocked | Sun is %s (Must be above_horizon)", self.name, sun_state.state

                 )
                 return False
            _LOGGER.debug("%s: Sun check pass (%s)", self.name, sun_state.state if sun_state else "None")

        # 2. Weather Check
        if self._weather_entity and self._allowed_weather:
            weather_state = self.hass.states.get(self._weather_entity)
            if not weather_state:
                 _LOGGER.warning("%s: Blocked | Weather entity %s unavailable", self.name, self._weather_entity)

                 return False
            
            if weather_state.state not in self._allowed_weather:
                 _LOGGER.warning(
                     "%s: Blocked | Weather is %s (Allowed: %s)",
                     self.name,
                     weather_state.state,
                     self._allowed_weather,
                 )
                 return False
            _LOGGER.debug("%s: Weather check pass (%s)", self.name, weather_state.state)

        return True

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        now = dt_util.now()
        _LOGGER.debug("%s: Request to Turn ON", self.name)

        # 1. Cooldown Check
        if self._is_cooldown_active():
             if self._cooldown_bypass:
                 _LOGGER.info(
                     "%s: Cooldown active but BYPASSED by user override (ticket consumed)", self.name
                 )
                 self._cooldown_bypass = False # Consume ticket
             else:
                 remaining = (self._last_run_time + self._cooldown) - now
                 _LOGGER.warning("%s: Blocked | Cooldown active. Remaining: %s", self.name, remaining)
                 return

        # 2. Environmental Check (Always enforced)
        if not self._check_environment():
            # If rejected by environment, we KEEP the bypass ticket for later? 
            # Or consume it? Let's keep it safe: Keep it.
            return

        # 3. Activation
        _LOGGER.debug("%s: Checks passed. Turning ON.", self.name)
        self._attr_is_on = True
        self._run_start_time = now
        self._cooldown_bypass = False # Reset just in case
        self.async_write_ha_state() # Optimistic update

        # Start Heartbeat if enabled
        if self._config.get(CONF_HEARTBEAT_ENABLED, True):
            _LOGGER.debug("%s: Starting heartbeat loop.", self.name)
            self._start_heartbeat()
        
        # Initial Pulse
        await self._pulse_target_on()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        self._stop_heartbeat()
        
        # Send OFF to hardware
        await self.hass.services.async_call(
            "switch",
            SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: self._target_entity},
            blocking=False, # Don't block for this
        )

        self._attr_is_on = False
        self._last_run_time = dt_util.now()
        self._run_start_time = None
        self.async_write_ha_state()

    def _start_heartbeat(self):
        """Start the heartbeat loop."""
        if self._heartbeat_remove_listener:
            return

        self._heartbeat_remove_listener = async_track_time_interval(
            self.hass,
            self._heartbeat_tick,
            self._heartbeat_interval,
        )

    def _stop_heartbeat(self):
        """Stop the heartbeat loop."""
        if self._heartbeat_remove_listener:
            self._heartbeat_remove_listener()
            self._heartbeat_remove_listener = None

    async def _heartbeat_tick(self, now: datetime):
        """Called periodically by heartbeat timer."""
        # 1. Run Limit Check
        if self._run_start_time and (now - self._run_start_time > self._run_limit):
             _LOGGER.info("Climate Guard Switch: Run limit reached (%s). Turning off.", self._run_limit)
             await self.async_turn_off()

             return

        # 2. Pulse Hardware
        await self._pulse_target_on()

    async def _pulse_target_on(self):
        """Send turn_on command to target entity."""
        try:
             await self.hass.services.async_call(
                "switch",
                SERVICE_TURN_ON,
                {ATTR_ENTITY_ID: self._target_entity},
                blocking=True, # Wait for it to ensure it was sent
            )
        except Exception as err:
             _LOGGER.warning("Climate Guard Switch: Failed to pulse target %s: %s", self._target_entity, err)



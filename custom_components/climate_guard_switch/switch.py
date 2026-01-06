"""Switch platform for Climate Guard Switch."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import GuardSwitchConfigEntry
from .const import DOMAIN, CONF_DEVICE_TYPE, DEVICE_TYPE_HEATER
from .coordinator import ClimateGuardCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: GuardSwitchConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Climate Guard Switch from a config entry."""
    async_add_entities([ClimateGuardSwitch(config_entry.runtime_data, config_entry)])


class ClimateGuardSwitch(CoordinatorEntity[ClimateGuardCoordinator], SwitchEntity, RestoreEntity):
    """Representation of the Guard Switch (Arm/Disarm)."""

    def __init__(self, coordinator: ClimateGuardCoordinator, config_entry: GuardSwitchConfigEntry) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_has_entity_name = True
        self._attr_name = None
        self._attr_unique_id = config_entry.entry_id
        
        self._device_type = config_entry.options.get(CONF_DEVICE_TYPE, config_entry.data.get(CONF_DEVICE_TYPE, DEVICE_TYPE_HEATER))

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name=config_entry.title,
            manufacturer="Custom",
            model="Climate Guard Switch",
        )

    @property
    def icon(self) -> str | None:
        """Return the icon to use in the frontend."""
        # Use target_active to show "activity", or guard_enabled to show "armed"?
        # User implies Switch = Guard State.
        # Let's show "Fire" if active, "Fire Off" if not active?
        # Or Shield?
        # Previous logic: Fire if active.
        is_active = self.coordinator.data["target_active"]
        
        if self._device_type == DEVICE_TYPE_HEATER:
            return "mdi:fire" if is_active else "mdi:fire-off"
        return "mdi:snowflake" if is_active else "mdi:snowflake-off"

    @property
    def is_on(self) -> bool:
        """Return true if switch is on (Guard Enabled)."""
        return self.coordinator.data["guard_enabled"]

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the Guard."""
        self.coordinator.set_guard_state(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the Guard."""
        self.coordinator.set_guard_state(False)
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore state."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        
        if last_state:
            is_on = last_state.state == "on"
            last_run_ts = last_state.attributes.get("last_run_time")
            last_run = dt_util.parse_datetime(last_run_ts) if last_run_ts else None
            
            # Seed the coordinator
            self.coordinator.set_guard_state(is_on, last_run)
            
    # Note: extra_state_attributes moved to Sensor/Coordinator Logic. 
    # But last_run_time is needed for restore. 
    # The Coordinator data has it. We should expose it in attributes so it gets saved.
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return attributes for restoration."""
        return {
            "last_run_time": self.coordinator.data["last_run"].isoformat() if self.coordinator.data["last_run"] else None
        }

"""Sensor platform for Climate Guard Switch."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import GuardSwitchConfigEntry
from .const import DOMAIN
from .coordinator import ClimateGuardCoordinator

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: GuardSwitchConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Climate Guard Switch sensor entities."""
    async_add_entities([GuardStatusSensor(config_entry.runtime_data, config_entry)])


class GuardStatusSensor(CoordinatorEntity[ClimateGuardCoordinator], SensorEntity):
    """Representation of the Guard Status Sensor."""

    def __init__(self, coordinator: ClimateGuardCoordinator, config_entry: GuardSwitchConfigEntry) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._attr_has_entity_name = True
        self._attr_name = "Status"
        self._attr_unique_id = f"{config_entry.entry_id}_status"
        self._attr_translation_key = "status"
        
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name=config_entry.title,
            manufacturer="Custom",
            model="Climate Guard Switch",
        )

    @property
    def native_value(self) -> str | None:
        """Return the state."""
        return self.coordinator.data.get("status")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return attributes."""
        data = self.coordinator.data
        return {
            "reason": data.get("reason"),
            "cooldown_active": data.get("cooldown_active"),
            "last_run": data.get("last_run").isoformat() if data.get("last_run") else None,
        }

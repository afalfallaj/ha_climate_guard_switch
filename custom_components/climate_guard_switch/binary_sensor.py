"""Binary Sensor platform for Climate Guard Switch."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
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
    """Set up the Climate Guard Switch binary sensor entities."""
    async_add_entities([GuardActiveSensor(config_entry.runtime_data, config_entry)])


class GuardActiveSensor(CoordinatorEntity[ClimateGuardCoordinator], BinarySensorEntity):
    """Representation of the Guard Active Binary Sensor (Hardware State)."""

    def __init__(self, coordinator: ClimateGuardCoordinator, config_entry: GuardSwitchConfigEntry) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._attr_has_entity_name = True
        self._attr_name = "Active"
        self._attr_unique_id = f"{config_entry.entry_id}_active"
        self._attr_translation_key = "active"
        self._attr_device_class = BinarySensorDeviceClass.RUNNING
        
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name=config_entry.title,
            manufacturer="Custom",
            model="Climate Guard Switch",
        )

    @property
    def is_on(self) -> bool | None:
        """Return the state."""
        return self.coordinator.data.get("target_active")

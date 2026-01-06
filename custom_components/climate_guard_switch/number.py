"""Number platform for Climate Guard Switch."""
from __future__ import annotations

from typing import cast

from homeassistant.components.number import NumberEntity, NumberMode, RestoreNumber
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import GuardSwitchConfigEntry
from .const import DOMAIN, CONF_TARGET_ENTITY, CONF_DEVICE_TYPE

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: GuardSwitchConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Climate Guard Switch number entities."""
    async_add_entities(
        [
            GuardSwitchNumber(
                config_entry,
                "run_limit",
                "Run Limit",
                "run_limit_minutes",
                UnitOfTime.MINUTES,
                1,
                120,
            ),
            GuardSwitchNumber(
                config_entry,
                "cooldown",
                "Cooldown",
                "cooldown_minutes",
                UnitOfTime.MINUTES,
                0,
                300,
            ),
             GuardSwitchNumber(
                config_entry,
                "heartbeat",
                "Heartbeat Interval",
                "heartbeat_interval_seconds",
                UnitOfTime.SECONDS,
                5,
                60,
            ),
        ]
    )


class GuardSwitchNumber(RestoreNumber):
    """Representation of a Climate Guard Switch Number entity."""

    def __init__(
        self,
        config_entry: GuardSwitchConfigEntry,
        key: str,
        name: str,
        translation_key: str,
        unit_of_measurement: str | None,
        min_value: float,
        max_value: float,
    ) -> None:
        """Initialize the number."""
        self._config_entry = config_entry
        self._key = key
        self._attr_translation_key = key # Using key as translation key part
        self._attr_has_entity_name = True
        self._attr_name = name
        self._attr_unique_id = f"{config_entry.entry_id}_{key}"
        self._attr_native_unit_of_measurement = unit_of_measurement
        self._attr_native_min_value = min_value
        self._attr_native_max_value = max_value
        self._attr_mode = NumberMode.BOX
        
        # Initial value from runtime data
        current_val = getattr(config_entry.runtime_data, key if key != "heartbeat" else "heartbeat_interval")
        self._attr_native_value = float(current_val)

        # Device Info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name=config_entry.title,
            manufacturer="Custom",
            model="Climate Guard Switch",
        )

    async def async_added_to_hass(self) -> None:
        """Restore last state."""
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_number_data()) is not None:
            self._attr_native_value = last_state.native_value
            self._update_runtime_data()

    async def async_set_native_value(self, value: float) -> None:
        """Update value."""
        self._attr_native_value = value
        self._update_runtime_data()
        self.async_write_ha_state()

    def _update_runtime_data(self) -> None:
        """Update the shared runtime data."""
        attr_name = self._key if self._key != "heartbeat" else "heartbeat_interval"
        setattr(self._config_entry.runtime_data, attr_name, int(self._attr_native_value))

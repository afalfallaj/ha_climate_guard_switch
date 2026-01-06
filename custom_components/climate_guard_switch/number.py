"""Number platform for Climate Guard Switch."""
from __future__ import annotations

from typing import cast

from homeassistant.components.number import NumberEntity, NumberMode, RestoreNumber
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_COOLDOWN,
    CONF_RUN_LIMIT,
    DEFAULT_COOLDOWN,
    DEFAULT_RUN_LIMIT,
    DOMAIN,
)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Climate Guard Switch number entities."""
    
    async_add_entities(
        [
            GuardSwitchNumber(
                config_entry,
                key=CONF_RUN_LIMIT,
                translation_key="run_limit",
                unit_of_measurement=UnitOfTime.MINUTES,
                min_value=0,
                max_value=120,
                default_value=DEFAULT_RUN_LIMIT,
            ),
            GuardSwitchNumber(
                config_entry,
                key=CONF_COOLDOWN,
                translation_key="cooldown",
                unit_of_measurement=UnitOfTime.MINUTES,
                min_value=0,
                max_value=300,
                default_value=DEFAULT_COOLDOWN,
            ),
        ]
    )


class GuardSwitchNumber(RestoreNumber):
    """Representation of a Climate Guard Switch Number entity."""

    def __init__(
        self,
        config_entry: ConfigEntry,
        key: str,
        translation_key: str,
        unit_of_measurement: str | None,
        min_value: float,
        max_value: float,
        default_value: int,
    ) -> None:
        """Initialize the number."""
        self._config_entry = config_entry
        self._key = key
        self._attr_translation_key = translation_key
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{config_entry.entry_id}_{key}"        
        self._attr_native_unit_of_measurement = unit_of_measurement
        self._attr_native_min_value = min_value
        self._attr_native_max_value = max_value
        self._attr_mode = NumberMode.BOX
        self._default_value = default_value

    @property
    def native_value(self) -> float:
        """Return the value."""
        # Read from options, fallback to data, fallback to default
        val = self._config_entry.options.get(self._key, self._config_entry.data.get(self._key, self._default_value))
        return float(val)

    async def async_set_native_value(self, value: float) -> None:
        """Update value."""
        # Update Options
        new_options = {**self._config_entry.options}
        new_options[self._key] = int(value)
        
        # This will trigger reload of the entry
        await self.hass.config_entries.async_update_entry(
            self._config_entry, options=new_options
        )

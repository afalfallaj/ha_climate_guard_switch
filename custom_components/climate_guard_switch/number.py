"""Number platform for Climate Guard Switch."""
from __future__ import annotations

from typing import Any, cast

from homeassistant.components.number import NumberEntity, NumberMode, RestoreNumber
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
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
                entity_category=EntityCategory.CONFIG,
                description=(
                    "0 disables this limit — the guard will never force a stop "
                    "on its own. Also requires the Heartbeat Interval option "
                    "(Settings > this device > Configure) to be above 0 seconds "
                    "to actually be enforced, even when this is set above 0."
                ),
            ),
            GuardSwitchNumber(
                config_entry,
                key=CONF_COOLDOWN,
                translation_key="cooldown",
                unit_of_measurement=UnitOfTime.MINUTES,
                min_value=0,
                max_value=300,
                default_value=DEFAULT_COOLDOWN,
                entity_category=EntityCategory.CONFIG,
                description=(
                    "0 disables the minimum rest period between runs. Cycling "
                    "speed is then controlled entirely by your thermostat's own "
                    "hysteresis / min_cycle_duration."
                ),
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
        entity_category: EntityCategory | None = None,
        description: str | None = None,
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
        self._attr_native_step = 1
        self._attr_mode = NumberMode.BOX
        self._attr_entity_category = entity_category
        self._description = description

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name=config_entry.title,
            manufacturer="Custom",
            model="Climate Guard Switch",
        )

        self._default_value = default_value

    @property
    def native_value(self) -> float:
        """Return the value."""
        # Read from options, fallback to data, fallback to default
        val = self._config_entry.options.get(self._key, self._config_entry.data.get(self._key, self._default_value))
        return float(val)

    @property
    def icon(self) -> str:
        """Return an icon reflecting whether this limit is currently disabled (0)."""
        return "mdi:timer-off-outline" if self.native_value == 0 else "mdi:timer-outline"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Explain what 0 means for this entity, visible in its more-info dialog."""
        if not self._description:
            return {}
        return {"description": self._description}

    async def async_set_native_value(self, value: float) -> None:
        """Update value."""
        # Update Options
        new_options = {**self._config_entry.options}
        new_options[self._key] = int(value)

        # This will trigger reload of the entry
        self.hass.config_entries.async_update_entry(
            self._config_entry, options=new_options
        )

        # This entity has no other refresh path (plain RestoreNumber, not a
        # CoordinatorEntity), so without this the edited value never reaches
        # the entity's displayed state.
        self.async_write_ha_state()

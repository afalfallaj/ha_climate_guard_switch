"""Sensor platform for Climate Guard Switch."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, PERCENTAGE
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import GuardSwitchConfigEntry
from .const import (
    CONF_CLIMATE_ENTITY,
    CONF_COOLING_ENTITY,
    CONF_HEATING_ENTITY,
    DOMAIN,
)
from .coordinator import ClimateGuardCoordinator
from .history import (
    history_config,
    history_device_info,
    is_history_entry,
    is_on,
    read_float_attribute,
    source_available,
)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: GuardSwitchConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Climate Guard Switch sensor entities."""
    if is_history_entry(config_entry):
        async_add_entities(_history_sensors(config_entry))
        return

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
            "cooldown_enabled": data.get("cooldown_enabled"),
            "run_limit_enabled": data.get("run_limit_enabled"),
            "run_limit_enforced": data.get("run_limit_enforced"),
        }


def _history_sensors(config_entry: ConfigEntry) -> list[HistorySensor]:
    """The statistics sensors a History view gets: one per configured input.

    These exist because only sensors with a state class get long-term statistics
    (kept forever, unlike the raw states behind the climate chart), so they are
    what keeps the history viewable over long date ranges.
    """
    config = history_config(config_entry)
    sensors: list[HistorySensor] = []
    if thermostat := config.get(CONF_CLIMATE_ENTITY):
        sensors.append(HistoryTargetTemperatureSensor(config_entry, thermostat))
    if heating := config.get(CONF_HEATING_ENTITY):
        sensors.append(HistoryActivitySensor(config_entry, heating, "heating"))
    if cooling := config.get(CONF_COOLING_ENTITY):
        sensors.append(HistoryActivitySensor(config_entry, cooling, "cooling"))
    return sensors


class HistorySensor(SensorEntity):
    """Read-only sensor derived from one source entity of a History view."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, config_entry: ConfigEntry, source: str, key: str) -> None:
        """Initialize."""
        self._source = source
        self._attr_unique_id = f"{config_entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = history_device_info(config_entry)

    @property
    def _source_state(self) -> State | None:
        return self.hass.states.get(self._source)

    @property
    def available(self) -> bool:
        """Unavailable while the source is, so no bogus value reaches the statistics."""
        return source_available(self._source_state)

    async def async_added_to_hass(self) -> None:
        """Follow the source entity."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._source], self._handle_source_change
            )
        )

    @callback
    def _handle_source_change(self, event: Event) -> None:
        self.async_write_ha_state()


class HistoryTargetTemperatureSensor(HistorySensor):
    """The linked thermostat's target temperature, kept as long-term statistics."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_suggested_display_precision = 1

    def __init__(self, config_entry: ConfigEntry, thermostat: str) -> None:
        """Initialize."""
        super().__init__(config_entry, thermostat, "target_temperature")

    @property
    def native_unit_of_measurement(self) -> str:
        """The thermostat reports its targets in the system unit."""
        return self.hass.config.units.temperature_unit

    @property
    def native_value(self) -> float | None:
        """Return the thermostat's target temperature."""
        return read_float_attribute(self._source_state, ATTR_TEMPERATURE)


class HistoryActivitySensor(HistorySensor):
    """100 while the heating/cooling entity is on, 0 otherwise.

    Long-term statistics store the hourly *mean* of this, so the value seen for
    an old hour is the share of that hour the equipment ran (50 = half an hour).
    """

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_suggested_display_precision = 0

    def __init__(self, config_entry: ConfigEntry, source: str, key: str) -> None:
        """Initialize; `key` is "heating" or "cooling"."""
        super().__init__(config_entry, source, key)
        self._attr_icon = "mdi:fire" if key == "heating" else "mdi:snowflake"

    @property
    def native_value(self) -> int:
        """Return 100 while the source is on."""
        return 100 if is_on(self._source_state) else 0

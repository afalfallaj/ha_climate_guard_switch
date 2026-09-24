"""Sensor platform for Climate Guard Switch."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE
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
    CONF_TEMPERATURE_SENSOR,
    DOMAIN,
)
from .coordinator import ClimateGuardCoordinator
from .history import (
    history_config,
    history_device_info,
    is_history_entry,
    read_float_attribute,
    source_available,
    trace_temperature,
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
    """The sensors of a History view: one per configured optional input.

    Only sensors get long-term statistics (kept forever, unlike raw states), and
    Home Assistant draws values of one kind in one chart. Publishing the target
    and the heating/cooling periods *as temperatures* is what lets a card show
    them together with the temperature, for any date range.
    """
    config = history_config(config_entry)
    temperature = config.get(CONF_TEMPERATURE_SENSOR)
    thermostat = config.get(CONF_CLIMATE_ENTITY)
    heating = config.get(CONF_HEATING_ENTITY)
    cooling = config.get(CONF_COOLING_ENTITY)

    sensors: list[HistorySensor] = []
    if thermostat:
        sensors.append(HistoryTargetTemperatureSensor(config_entry, thermostat))
    if temperature and heating:
        sensors.append(HistoryTraceSensor(config_entry, temperature, heating, "temperature_while_heating"))
    if temperature and cooling:
        sensors.append(HistoryTraceSensor(config_entry, temperature, cooling, "temperature_while_cooling"))
    return sensors


class HistorySensor(SensorEntity):
    """Read-only temperature sensor derived from the source entities of a History view."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_suggested_display_precision = 1

    def __init__(self, config_entry: ConfigEntry, sources: tuple[str, ...], key: str) -> None:
        """Initialize; `sources` are the entity ids this sensor derives from."""
        self._sources = sources
        self._attr_unique_id = f"{config_entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = history_device_info(config_entry)

    def _state_of(self, index: int) -> State | None:
        return self.hass.states.get(self._sources[index])

    @property
    def _source_state(self) -> State | None:
        return self._state_of(0)

    @property
    def native_unit_of_measurement(self) -> str:
        """The system unit: the same one the temperature sensor is charted in."""
        return self.hass.config.units.temperature_unit

    @property
    def available(self) -> bool:
        """Unavailable while any source is, so no bogus value reaches the statistics."""
        return all(source_available(self._state_of(i)) for i in range(len(self._sources)))

    async def async_added_to_hass(self) -> None:
        """Follow the source entities."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, list(self._sources), self._handle_source_change
            )
        )

    @callback
    def _handle_source_change(self, event: Event) -> None:
        self.async_write_ha_state()


class HistoryTargetTemperatureSensor(HistorySensor):
    """The linked thermostat's target temperature (the target line), kept as statistics."""

    def __init__(self, config_entry: ConfigEntry, thermostat: str) -> None:
        """Initialize."""
        super().__init__(config_entry, (thermostat,), "target_temperature")

    @property
    def native_value(self) -> float | None:
        """Return the thermostat's target temperature (already in the system unit)."""
        return read_float_attribute(self._source_state, ATTR_TEMPERATURE)


class HistoryTraceSensor(HistorySensor):
    """The temperature, present only while the heating (or cooling) entity is on.

    Home Assistant draws values of one kind in one chart and keeps long-term
    statistics only for sensors. A temperature that exists only while the
    equipment runs therefore lets a card mark the heating/cooling periods (red
    and blue) inside the temperature chart for any date range: list it after
    the temperature in a history-graph card, or in a statistics-graph card with
    period: hour. Idle time is `unknown`, never a made-up number.
    """

    def __init__(self, config_entry: ConfigEntry, temperature_sensor: str, activity: str, key: str) -> None:
        """Initialize; `key` is "temperature_while_heating" or "temperature_while_cooling"."""
        super().__init__(config_entry, (temperature_sensor, activity), key)
        self._attr_icon = (
            "mdi:thermometer-chevron-up" if key == "temperature_while_heating" else "mdi:thermometer-chevron-down"
        )

    @property
    def native_value(self) -> float | None:
        """The temperature while the activity entity is on, else None."""
        return trace_temperature(self.hass, self._sources[0], self._state_of(1), self.native_unit_of_measurement)

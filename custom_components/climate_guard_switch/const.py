"""Constants for the Climate Guard Switch integration."""
from homeassistant.const import Platform

DOMAIN = "climate_guard_switch"

CONF_TARGET_ENTITY = "target_entity"
CONF_SUN_ENTITY = "sun_entity"
CONF_WEATHER_ENTITY = "weather_entity"
CONF_RUN_LIMIT = "run_limit_minutes"
CONF_COOLDOWN = "cooldown_minutes"
CONF_HEARTBEAT = "heartbeat_interval_seconds"
CONF_CLIMATE_ENTITY = "climate_entity"

CONF_DEVICE_TYPE = "device_type"
CONF_ALLOWED_WEATHER = "allowed_weather_states"

# Entry types. Guard entries predate this key and don't carry it, so a missing
# CONF_ENTRY_TYPE always means "guard" — no migration needed.
CONF_ENTRY_TYPE = "entry_type"
ENTRY_TYPE_GUARD = "guard"
ENTRY_TYPE_HISTORY = "history"

# History view entry: read-only mirror of entities from any integration.
CONF_TEMPERATURE_SENSOR = "temperature_sensor"
CONF_HEATING_ENTITY = "heating_entity"
CONF_COOLING_ENTITY = "cooling_entity"
# "Temperature while heating/cooling" sensors for long-range single-chart views.
# Absent means on, so views created before the option existed get them too.
CONF_TEMPERATURE_TRACES = "temperature_traces"

DEVICE_TYPE_HEATER = "heater"
DEVICE_TYPE_COOLER = "cooler"

DEFAULT_RUN_LIMIT = 10
DEFAULT_COOLDOWN = 40
DEFAULT_HEARTBEAT = 10
DEFAULT_HISTORY_NAME = "Climate History"

PLATFORMS: list[Platform] = [
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]

# History entries have no coordinator and no controls: just a read-only climate
# entity (the combined history chart) plus statistics sensors.
HISTORY_PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.SENSOR,
]

# Standard HA Weather States
WEATHER_STATES = [
    "clear-night",
    "cloudy",
    "fog",
    "hail",
    "lightning",
    "lightning-rainy",
    "partlycloudy",
    "pouring",
    "rainy",
    "snowy",
    "snowy-rainy",
    "sunny",
    "windy",
    "windy-variant",
    "exceptional",
]

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
# Optional temperature for the history chart sensors; the linked thermostat's
# current temperature is used when it is not set.
CONF_TEMPERATURE_SENSOR = "temperature_sensor"

CONF_DEVICE_TYPE = "device_type"
CONF_ALLOWED_WEATHER = "allowed_weather_states"

# v0.0.4 to v0.0.6 could create a separate "History view" entry, marked with
# this key. Such entries are no longer supported: setup fails with a message
# asking to delete them (the sensors now live on the guard device).
CONF_ENTRY_TYPE = "entry_type"
ENTRY_TYPE_HISTORY = "history"

DEVICE_TYPE_HEATER = "heater"
DEVICE_TYPE_COOLER = "cooler"

DEFAULT_RUN_LIMIT = 10
DEFAULT_COOLDOWN = 40
DEFAULT_HEARTBEAT = 10

PLATFORMS: list[Platform] = [
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
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

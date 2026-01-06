"""Constants for the Climate Guard Switch integration."""

DOMAIN = "climate_guard_switch"

CONF_TARGET_ENTITY = "target_entity"
CONF_SUN_ENTITY = "sun_entity"
CONF_WEATHER_ENTITY = "weather_entity"
CONF_RUN_LIMIT = "run_limit_minutes"
CONF_COOLDOWN = "cooldown_minutes"
CONF_HEARTBEAT = "heartbeat_interval_seconds"
CONF_HEARTBEAT_ENABLED = "heartbeat_enabled"
CONF_CLIMATE_ENTITY = "climate_entity"

CONF_DEVICE_TYPE = "device_type"
CONF_ALLOWED_WEATHER = "allowed_weather_states"

DEVICE_TYPE_HEATER = "heater"
DEVICE_TYPE_COOLER = "cooler"

DEFAULT_RUN_LIMIT = 10
DEFAULT_COOLDOWN = 40
DEFAULT_HEARTBEAT = 10

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

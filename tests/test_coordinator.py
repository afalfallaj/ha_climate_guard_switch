"""Tests for custom_components/climate_guard_switch/coordinator.py.

Covers the sun/weather/cooldown gating logic and the run-limit/cooldown-reads-
live-options behavior — the parts flagged in AGENTS.md as safety-relevant and
easy to silently break.
"""
from __future__ import annotations

import asyncio
from datetime import timedelta

from homeassistant.util import dt as dt_util

from custom_components.climate_guard_switch.coordinator import ClimateGuardCoordinator
from custom_components.climate_guard_switch.const import (
    CONF_ALLOWED_WEATHER,
    CONF_CLIMATE_ENTITY,
    CONF_COOLDOWN,
    CONF_HEARTBEAT,
    CONF_RUN_LIMIT,
    CONF_SUN_ENTITY,
    CONF_TARGET_ENTITY,
    CONF_WEATHER_ENTITY,
)

from conftest import _ConfigEntry, _HomeAssistant  # type: ignore[import]

TARGET_ENTITY = "switch.heater"
SUN_ENTITY = "sun.sun"
WEATHER_ENTITY = "weather.home"
CLIMATE_ENTITY = "climate.thermostat"


def _make_coordinator(**data_overrides) -> ClimateGuardCoordinator:
    hass = _HomeAssistant()
    data = {CONF_TARGET_ENTITY: TARGET_ENTITY, **data_overrides}
    entry = _ConfigEntry(data=data)
    return ClimateGuardCoordinator(hass, entry)


def test_no_gates_allows_by_default() -> None:
    coordinator = _make_coordinator()

    allowed, reason = coordinator._check_conditions()

    assert allowed is True
    assert reason is None


def test_sun_check_blocks_when_below_horizon() -> None:
    coordinator = _make_coordinator(**{CONF_SUN_ENTITY: SUN_ENTITY})
    coordinator.hass.states.set(SUN_ENTITY, "below_horizon")

    allowed, reason = coordinator._check_conditions()

    assert allowed is False
    assert "Sun is below_horizon" in reason


def test_sun_check_allows_above_horizon() -> None:
    coordinator = _make_coordinator(**{CONF_SUN_ENTITY: SUN_ENTITY})
    coordinator.hass.states.set(SUN_ENTITY, "above_horizon")

    allowed, _ = coordinator._check_conditions()

    assert allowed is True


def test_weather_check_blocks_when_not_in_allow_list() -> None:
    coordinator = _make_coordinator(
        **{CONF_WEATHER_ENTITY: WEATHER_ENTITY, CONF_ALLOWED_WEATHER: ["sunny"]}
    )
    coordinator.hass.states.set(WEATHER_ENTITY, "rainy")

    allowed, reason = coordinator._check_conditions()

    assert allowed is False
    assert "Weather is rainy" in reason


def test_weather_check_ignored_when_allow_list_empty() -> None:
    coordinator = _make_coordinator(**{CONF_WEATHER_ENTITY: WEATHER_ENTITY, CONF_ALLOWED_WEATHER: []})
    coordinator.hass.states.set(WEATHER_ENTITY, "rainy")

    allowed, _ = coordinator._check_conditions()

    assert allowed is True


def test_cooldown_blocks_immediately_after_a_run() -> None:
    coordinator = _make_coordinator(**{CONF_COOLDOWN: 40})
    coordinator._last_run_time = dt_util.now()

    allowed, reason = coordinator._check_conditions()

    assert allowed is False
    assert "Cooldown" in reason


def test_cooldown_zero_disables_the_gate() -> None:
    coordinator = _make_coordinator(**{CONF_COOLDOWN: 0})
    coordinator._last_run_time = dt_util.now()

    allowed, _ = coordinator._check_conditions()

    assert allowed is True


def test_cooldown_bypass_allows_immediate_restart() -> None:
    coordinator = _make_coordinator(**{CONF_COOLDOWN: 40})
    coordinator._last_run_time = dt_util.now()
    coordinator._cooldown_bypass = True

    allowed, _ = coordinator._check_conditions()

    assert allowed is True


def test_cooldown_expires_after_the_configured_window() -> None:
    coordinator = _make_coordinator(**{CONF_COOLDOWN: 40})
    coordinator._last_run_time = dt_util.now() - timedelta(minutes=41)

    allowed, _ = coordinator._check_conditions()

    assert allowed is True


async def test_climate_temperature_change_sets_cooldown_bypass() -> None:
    coordinator = _make_coordinator(**{CONF_CLIMATE_ENTITY: CLIMATE_ENTITY})

    class _FakeEvent:
        def __init__(self, old_temp, new_temp) -> None:
            self.data = {
                "entity_id": CLIMATE_ENTITY,
                "old_state": type("S", (), {"attributes": {"temperature": old_temp}})(),
                "new_state": type("S", (), {"attributes": {"temperature": new_temp}})(),
            }

    await coordinator._on_dependency_change(_FakeEvent(20, 22))

    assert coordinator._cooldown_bypass is True


def test_run_limit_and_cooldown_read_live_from_options_without_reload() -> None:
    """Regression: number.py writes straight to entry.options with no reload —
    the coordinator instance must reflect that on its next property access."""
    coordinator = _make_coordinator(**{CONF_RUN_LIMIT: 10, CONF_COOLDOWN: 40})

    assert coordinator.run_limit == timedelta(minutes=10)
    assert coordinator.cooldown == timedelta(minutes=40)

    coordinator.config_entry.options[CONF_RUN_LIMIT] = 25
    coordinator.config_entry.options[CONF_COOLDOWN] = 5

    assert coordinator.run_limit == timedelta(minutes=25)
    assert coordinator.cooldown == timedelta(minutes=5)


def test_update_data_reports_enabled_flags() -> None:
    coordinator = _make_coordinator(**{CONF_RUN_LIMIT: 10, CONF_COOLDOWN: 40})
    coordinator._update_data()
    assert coordinator.data["cooldown_enabled"] is True
    assert coordinator.data["run_limit_enabled"] is True
    assert coordinator.data["run_limit_enforced"] is True  # default heartbeat > 0


def test_update_data_disabled_flags_when_zero() -> None:
    coordinator = _make_coordinator(**{CONF_RUN_LIMIT: 0, CONF_COOLDOWN: 0})
    coordinator._update_data()
    assert coordinator.data["cooldown_enabled"] is False
    assert coordinator.data["run_limit_enabled"] is False
    assert coordinator.data["run_limit_enforced"] is False


def test_update_data_run_limit_not_enforced_when_heartbeat_disabled() -> None:
    """Regression: run-limit enforcement lives inside the heartbeat tick, so
    heartbeat=0 silently disables it even with run_limit > 0."""
    coordinator = _make_coordinator(**{CONF_RUN_LIMIT: 10, CONF_HEARTBEAT: 0})
    coordinator._update_data()
    assert coordinator.data["run_limit_enabled"] is True
    assert coordinator.data["run_limit_enforced"] is False
    assert "not enforced" in coordinator.data["status"].lower()


async def test_set_guard_state_updates_data_synchronously() -> None:
    """Regression: switch.py reads coordinator.data right after calling
    set_guard_state(), before the scheduled background task gets to run."""
    coordinator = _make_coordinator()
    assert coordinator.data["guard_enabled"] is False

    coordinator.set_guard_state(True)

    # No `await` yet — the background task scheduled by set_guard_state()
    # hasn't run, mirroring switch.py's immediate async_write_ha_state() call.
    assert coordinator.data["guard_enabled"] is True

    await asyncio.sleep(0)  # let the scheduled task finish before the test exits


async def test_heartbeat_tick_stops_target_once_run_limit_exceeded() -> None:
    from homeassistant.util import dt as dt_util

    coordinator = _make_coordinator(**{CONF_RUN_LIMIT: 10})
    coordinator._guard_enabled = True
    coordinator._target_is_active = True
    coordinator._run_start_time = dt_util.now() - timedelta(minutes=11)

    await coordinator._heartbeat_tick(dt_util.now())

    assert coordinator._target_is_active is False
    coordinator.hass.services.async_call.assert_any_call(
        "switch", "turn_off", {"entity_id": TARGET_ENTITY}, blocking=False
    )


async def test_heartbeat_tick_keeps_running_within_run_limit() -> None:
    from homeassistant.util import dt as dt_util

    coordinator = _make_coordinator(**{CONF_RUN_LIMIT: 10})
    coordinator._guard_enabled = True
    coordinator._target_is_active = True
    coordinator._run_start_time = dt_util.now() - timedelta(minutes=2)

    await coordinator._heartbeat_tick(dt_util.now())

    assert coordinator._target_is_active is True

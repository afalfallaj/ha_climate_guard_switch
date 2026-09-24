# AGENTS.md

This file provides guidance to AI coding agents (Claude Code, Codex, etc.) when working with code in this repository.

## What this is

A Home Assistant custom integration (`custom_components/climate_guard_switch`) distributed via HACS. It wraps a physical `switch.*` entity as a "smart proxy" that adds safety logic (run limits, cooldowns, a heartbeat/dead-man's-switch pulse) and environmental gates (sun, weather, linked thermostat override) before allowing the underlying hardware switch to actually turn on.

It also offers an optional, read-only **History view** entry type (see "History view" below) that has nothing to do with the guard logic.

There is no build step or package manifest — it's pure Python targeting the Home Assistant runtime (`homeassistant` is provided by HA at runtime, not vendored or pinned here). Manual end-to-end verification happens by installing the folder into a real or dev HA instance's `config/custom_components/` and exercising it through the HA UI (Settings > Devices & Services); `tests/` covers the logic that doesn't need a real HA instance (see Testing below).

## Architecture

Everything for one configured device flows through a single `ClimateGuardCoordinator` (`coordinator.py`), a `DataUpdateCoordinator` with `update_interval=None` — it's event-driven, not polled. All platform entities (`switch.py`, `number.py`, `sensor.py`, `binary_sensor.py`) are thin `CoordinatorEntity` views over this one coordinator instance, stored on `entry.runtime_data` (see the `GuardSwitchConfigEntry = ConfigEntry[ClimateGuardCoordinator]` type alias in `__init__.py`).

Key state split to understand before touching logic:
- **`_guard_enabled`** — user-facing arm/disarm state, owned by `ClimateGuardSwitch` (the switch entity) and pushed into the coordinator via `coordinator.set_guard_state()`. This is what the switch's `is_on` reflects, restored on startup via `RestoreEntity`.
- **`_target_is_active`** — whether the coordinator has actually turned the real hardware switch on. Exposed via the binary sensor (`binary_sensor.py`, device class `RUNNING`) and used to derive icons/status text.
- The core decision loop is `_async_check_and_update()` → `_check_conditions()`, evaluated in order: sun check → weather check → cooldown check. Any gate failing sets `_block_reason` (surfaced on the status sensor) and stops the target if it was running.
- **Cooldown bypass**: changing the target temperature on the linked `climate_entity` sets `_cooldown_bypass = True` for one cycle (see `_on_dependency_change`), letting the user's manual override skip the rest period once.
- **Heartbeat**: when `_target_is_active`, `_ensure_heartbeat_running()` schedules `_heartbeat_tick` on `heartbeat_interval`. Each tick re-pulses the hardware switch `on` (so hardware-side auto-off timers get refreshed) and separately checks `run_limit` to force a stop if the run has gone on too long. If HA crashes, pulses stop and hardware auto-off (configured on the physical device, outside this integration) is the actual safety net — this integration only *drives* that pattern, it doesn't replace hardware-level protection.
- **Runtime-adjustable values**: `run_limit`, `cooldown`, and `heartbeat_interval` are properties that always read live from `config_entry.options` (falling back to `.data`, then a constant default), so the `number.py` entities can change them instantly with no reload at all — `async_set_native_value` calls `async_update_entry(options=...)` directly and nothing listens for that specific update, precisely so an in-progress run's `_run_start_time`/`_target_is_active` survive a slider tweak.

Config vs. options vs. reconfigure: `config_flow.py`'s `_get_config_schema()` is shared between the initial `ConfigFlow` (adds `device_type`, and sets the target entity as the flow's `unique_id` so the same switch can't be added twice — entries from before this existed are backfilled by `async_migrate_entry` in `__init__.py`, version 1 → 2) and the `OptionsFlowHandler` (everything else, editable later). `OptionsFlowHandler` extends `OptionsFlowWithReload`, so submitting the options form reloads the entry automatically — this is deliberately the *only* path that reloads; do not add a config-entry update listener back in `__init__.py`, since `OptionsFlowWithReload` raises if one is registered, and it would reintroduce reloading (and resetting in-memory run state) on every `number.py` slider change. Optional fields not resubmitted in the options form are explicitly nulled out (see the loop over `CONF_SUN_ENTITY`, `CONF_WEATHER_ENTITY`, `CONF_CLIMATE_ENTITY`, `CONF_ALLOWED_WEATHER` in `async_step_init`), and merged onto the *existing* options (`{**self.config_entry.options, **user_input}`) rather than replacing them outright, so options the form doesn't know about (like the number entities' run limit/cooldown) survive a save. `device_type` is the one field with neither a live path nor an options-form path to change it post-creation, so it gets its own minimal `async_step_reconfigure` (pattern borrowed from `smart_garage_door`'s `config_flow.py`) — deliberately scoped to just that field rather than duplicating the full schema, so there's exactly one place to edit each field.

All constants (config keys, defaults, platform lists, HA weather-state enum) live in `const.py` — check there first before adding a new config field.

`diagnostics.py` redacts `CONF_TARGET_ENTITY` and `unique_id`, and dumps an explicit, serializable snapshot of the coordinator's data plus live states of the target/sun/weather/climate entities — build the snapshot from named fields (never `vars(entry.runtime_data)`, which pulls in `hass` and a circular reference back to the entry itself). History entries branch off at the top and return just their config plus the live state of their input entities.

### History view (second entry type)

`ConfigFlow.async_step_user` is a menu: `guard` (the original form, moved verbatim to `async_step_guard`) or `history`. A history entry carries `entry_type: "history"` in its data (`is_history_entry()` in `history.py`); **guard entries have no `entry_type` key and absence means guard**, so no migration or version bump was needed and the guard path is untouched. History entries have **no coordinator, no `runtime_data`, no target switch and no `unique_id`** (their inputs are editable in options, so an id derived from them would go stale; several views are legitimate). `__init__.py`, `sensor.py`, `diagnostics.py` and `config_flow.py` each branch on `is_history_entry()` first — anything that assumes `entry.runtime_data` is a coordinator or reads `CONF_TARGET_ENTITY` must not be reached for a history entry. `HISTORY_PLATFORMS` is climate + sensor only.

Purpose: Home Assistant's built-in History page draws one combined chart for a `climate` entity (current temperature, target, and heating/cooling shading from `hvac_action`), so `climate.py`'s `HistoryClimate` assembles that chart from entities of *any* integration (a required temperature sensor; optional thermostat, heating and cooling entities — the relays are recommended, since they are what actually ran). Each viewer picks their own date range on the History page. The pure logic (unit conversion, mode/action derivation) lives in `history.py`. Rules to keep:
- **Strictly read-only, never a service call.** `supported_features` is `ClimateEntityFeature(0)` (no controls), `hvac_modes` holds only the current mode (so HA rejects any other `set_hvac_mode` before it reaches the no-op `async_set_hvac_mode`), and nothing in a history entry may ever call a service.
- The target line is published through `extra_state_attributes` (`temperature` / `target_temp_low` / `target_temp_high`, passed through from the thermostat) because HA only emits `temperature` itself when the target feature is advertised. `state-history-chart-line-data.ts` reads attributes only. **Risk:** if a future HA core blocks overriding those attributes, the fallback is advertising `TARGET_TEMPERATURE` with a set handler that raises `ServiceValidationError`.
- `hvac_action` comes from the real relays (heating wins if both are on; a running relay beats a thermostat that says off); with no relays configured it mirrors the thermostat's own `hvac_action`.
- Only *sensors* with a `state_class` get long-term statistics (kept forever, unlike the raw states the recorder purges after `purge_keep_days`), so the Target temperature and Heating/Cooling % (0/100, whose hourly mean is the share of the hour it ran) sensors are what make long date ranges work. There is deliberately no temperature mirror sensor: the source sensor has its own statistics. Nothing is backfilled and the integration never touches recorder config.
- The options flow is a separate `HistoryOptionsFlowHandler` (step `history`, so it doesn't clash with the guard's `options.step.init` strings); same null-out-then-merge pattern as the guard's, and still no update listener. `async_step_reconfigure` aborts for history entries.

Translatable strings (`strings.json`, `translations/en.json`) must stay in sync when adding/renaming a config field or entity `translation_key`.

The gating/cooldown/run-limit logic in `coordinator.py` (`_check_conditions`, `_is_cooldown_active`, `_heartbeat_tick`) is the safety-relevant core of this integration — it's what stands between a misconfiguration and equipment running longer or more often than intended. Prefer targeted, tested changes over rewrites here; `tests/test_coordinator.py` exists specifically to catch a change that silently alters this behavior.

## Testing

`tests/` uses `pytest` + `pytest-asyncio` with `homeassistant` stubbed via `sys.modules` in `tests/conftest.py` (real minimal classes where behavior matters — `ConfigEntry`, a working `DataUpdateCoordinator`, a fake `ConfigFlow`/`OptionsFlow`/unique_id registry — `MagicMock` otherwise), instead of depending on the heavy, HA-core-version-pinned `pytest-homeassistant-custom-component` package. This mirrors `smart_garage_door`'s approach and is what makes these tests runnable at all in an environment with no `homeassistant` package installed.

Run with:
```
pip install -r requirements_test.txt
pytest
```

Covers `coordinator.py`'s gating/cooldown/run-limit logic, `config_flow.py`'s unique_id/duplicate-detection, entry-type menu, reconfigure, and the options-merge fix (guard and history), `__init__.py`'s version migration and its guard-vs-history setup/unload split, `diagnostics.py`, and the whole History view (`history.py`'s helpers, `climate.py`'s read-only guarantees, and the history sensors in `sensor.py`) in `tests/test_history.py`. `conftest.py` provides real minimal stand-ins where behavior matters (the climate `HVACMode`/`HVACAction`/`ClimateEntityFeature` enums, entity base classes, a `TemperatureConverter` that raises like the real one) — keep them faithful when extending. The guard's thin `CoordinatorEntity` views (`switch.py`, `number.py`, `binary_sensor.py`, and `GuardStatusSensor` beyond its setup wiring) aren't covered, as they have little logic of their own; extend `conftest.py`'s stubs (`restore_state`, number/switch/binary_sensor bases) if that changes.

## Releases

`.github/workflows/tag_and_release.yml` (copied from `ha_gimdow_ble`) owns versioning:
- Push to `dev` → bumps a `-dev` prerelease tag and publishes a GitHub Pre-Release.
- Push to `main` → bumps a stable tag, rewrites `manifest.json`'s `version` (and any `__version__` in `__init__.py`, not currently present here) and `CHANGELOG.md`, commits that back to `main`, and publishes a GitHub Release.
- Commit messages should follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `refactor:`, etc.) since the action reads them to pick the version bump and to group the changelog.
- Don't hand-edit `manifest.json`'s `version` or create tags manually — the workflow owns both.

**Gotcha if this workflow is ever copied again**: the "Commit versions" step's `git add custom_components/*/__init__.py` glob depth must match this repo's actual layout — one level (`custom_components/climate_guard_switch/__init__.py`), same as `smart_garage_door`. `ha_gimdow_ble`'s copy of this same workflow uses `custom_components/*/*/__init__.py` (two levels) because *that* repo nests a same-named subpackage (`custom_components/gimdow_ble/gimdow_ble/`); pasted as-is here it matched nothing, `git add` failed on the missing pathspec, and the whole release step failed — this happened for real in `smart_garage_door`'s history (commit `688cd65`) before being fixed the same way. If a future refactor adds a nested subpackage, this glob needs to grow with it.

## Brand icon

`custom_components/climate_guard_switch/brand/` ships generated (not bespoke) brand images — see `brand/SOURCE.md` for the exact glyph, license, and generation steps. Since HA 2026.3, a custom integration's own `brand/` folder takes priority over the `home-assistant/brands` CDN automatically — no manifest change needed.

## HACS store listing

`info.md` is what HACS shows in its store UI *before* a user installs — keep it short and separate from `README.md` (the full docs, shown after/via the repo). Update both when user-facing behavior changes.

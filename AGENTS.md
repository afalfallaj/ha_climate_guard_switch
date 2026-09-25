# AGENTS.md

This file provides guidance to AI coding agents (Claude Code, Codex, etc.) when working with code in this repository.

## What this is

A Home Assistant custom integration (`custom_components/climate_guard_switch`) distributed via HACS. It wraps a physical `switch.*` entity as a "smart proxy" that adds safety logic (run limits, cooldowns, a heartbeat/dead-man's-switch pulse) and environmental gates (sun, weather, linked thermostat override) before allowing the underlying hardware switch to actually turn on.

Each guard device also carries read-only **history chart sensors** (see below) that have nothing to do with the guard logic.

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

Config vs. options vs. reconfigure: `config_flow.py`'s `_get_config_schema()` is shared between the initial `ConfigFlow` (adds `device_type`, and sets the target entity as the flow's `unique_id` so the same switch can't be added twice — entries from before this existed are backfilled by `async_migrate_entry` in `__init__.py`, version 1 → 2) and the `OptionsFlowHandler` (everything else, editable later). `OptionsFlowHandler` extends `OptionsFlowWithReload`, so submitting the options form reloads the entry automatically — this is deliberately the *only* path that reloads; do not add a config-entry update listener back in `__init__.py`, since `OptionsFlowWithReload` raises if one is registered, and it would reintroduce reloading (and resetting in-memory run state) on every `number.py` slider change. Optional fields not resubmitted in the options form are explicitly nulled out (see `OPTIONAL_ENTITY_FIELDS` and the loop in `async_step_init`), and merged onto the *existing* options (`{**self.config_entry.options, **user_input}`) rather than replacing them outright, so options the form doesn't know about (like the number entities' run limit/cooldown) survive a save. `device_type` is the one field with neither a live path nor an options-form path to change it post-creation, so it gets its own minimal `async_step_reconfigure` (pattern borrowed from `smart_garage_door`'s `config_flow.py`) — deliberately scoped to just that field rather than duplicating the full schema, so there's exactly one place to edit each field.

All constants (config keys, defaults, platform lists, HA weather-state enum) live in `const.py` — check there first before adding a new config field.

`diagnostics.py` redacts `CONF_TARGET_ENTITY` and `unique_id`, and dumps an explicit, serializable snapshot of the coordinator's data plus live states of the target/sun/weather/climate entities — build the snapshot from named fields (never `vars(entry.runtime_data)`, which pulls in `hass` and a circular reference back to the entry itself). History entries branch off at the top and return just their config plus the live state of their input entities.

### History chart sensors (on the guard device)

Purpose: let HA's *built-in* cards show a temperature, its target and the heating/cooling periods in ONE chart for any date range. HA draws values of one kind per chart and keeps long-term statistics only for sensors, so `sensor.py`'s `_chart_sensors()` turns what the guard already knows into temperature sensors (`state_class = measurement`, `device_class = temperature`, system unit, visible, no category): `HistoryTargetTemperatureSensor` (the linked thermostat's target, unique id `<entry_id>_target_temperature`) and `HistoryTraceSensor` (unique id `<entry_id>_temperature_while_running`, translation key/icon by `device_type`: `temperature_while_heating` or `temperature_while_cooling`; the temperature only while the hardware relay `CONF_TARGET_ENTITY` is on, `None` = state `unknown` otherwise). The temperature comes from the optional `CONF_TEMPERATURE_SENSOR` (converted to the system unit) or, when that is empty, the thermostat's `current_temperature` attribute. The pure logic lives in `history.py`. Rules to keep:
- **Read-only, never a service call**, and they follow the **hardware relay's real state**, not the coordinator (`Active` has a known stale-state bug after a run-limit stop; the relay is the truth of what ran). They are plain `SensorEntity`s, not `CoordinatorEntity`s.
- No fake values: a trace is `None` when idle and unavailable when a source is unavailable.
- Card recipes must pin `period: hour` — day/month statistics rows are adjacent and join across idle days. A History-page device pick joins the statistics segments across idle hours (the README says so and points to the cards).
- Prototyped on HA 2026.9.3 + frontend 20260826.7 with a scratch `pytest-homeassistant-custom-component` harness (real recorder + statistics import) and the frontend's own chart builders bundled in Node: rows exist only for hours with activity; hourly mean = `avg()` of 5-minute buckets; carry-forward at most 5 minutes; `statistics-graph` draws a gap between non-adjacent rows, the History page does not.
- History: v0.0.4–v0.0.6 shipped these sensors on a separate "History view" config entry (`entry_type: "history"` in its data; also a climate entity and % sensors in v0.0.4). That entry type is gone. `is_history_entry()` still detects such leftovers: `async_setup_entry` raises `ConfigEntryError(translation_key="history_view_removed")` (message in the `exceptions` section of the strings) and the options/reconfigure flows abort with the same reason, so the user deletes the entry (HA then removes its entities). Keep that until no v0.0.4–v0.0.6 installs remain.

Translatable strings (`strings.json`, `translations/en.json`) must stay identical and complete when adding/renaming a config field, flow step, menu option, abort reason or entity `translation_key`. For a custom integration Home Assistant reads only `translations/en.json` at runtime, and a missing or empty key is not an error — it silently renders as blank text (blank menu buttons, blank field labels, an empty message after Reconfigure). A stale or incomplete file, or a running HA that still has the old one cached (translations are read once per process, so restart after updating), produces exactly the "Add device shows empty strings" symptom. `tests/test_translations.py` enforces sync and coverage; abort reasons Home Assistant raises itself rather than our code (`already_configured`, `already_in_progress`, `reconfigure_successful`) are listed in its `HA_RAISED_ABORTS` — add to that list if a new flow call can raise another.

The gating/cooldown/run-limit logic in `coordinator.py` (`_check_conditions`, `_is_cooldown_active`, `_heartbeat_tick`) is the safety-relevant core of this integration — it's what stands between a misconfiguration and equipment running longer or more often than intended. Prefer targeted, tested changes over rewrites here; `tests/test_coordinator.py` exists specifically to catch a change that silently alters this behavior.

## Testing

`tests/` uses `pytest` + `pytest-asyncio` with `homeassistant` stubbed via `sys.modules` in `tests/conftest.py` (real minimal classes where behavior matters — `ConfigEntry`, a working `DataUpdateCoordinator`, a fake `ConfigFlow`/`OptionsFlow`/unique_id registry — `MagicMock` otherwise), instead of depending on the heavy, HA-core-version-pinned `pytest-homeassistant-custom-component` package. This mirrors `smart_garage_door`'s approach and is what makes these tests runnable at all in an environment with no `homeassistant` package installed.

Run with:
```
pip install -r requirements_test.txt
pytest
```

Covers `coordinator.py`'s gating/cooldown/run-limit logic, `config_flow.py`'s unique_id/duplicate-detection, reconfigure, the options-merge fix and the leftover-History-view rejection, `__init__.py`'s version migration and setup/unload, `diagnostics.py`, translation coverage (`tests/test_translations.py`), and the history chart sensors (`history.py`'s helpers and the sensors in `sensor.py`) in `tests/test_history.py`. `conftest.py` provides real minimal stand-ins where behavior matters (entity base classes, a `TemperatureConverter` that raises like the real one, a `ConfigEntryError` with the translation kwargs) — keep them faithful when extending. The guard's thin `CoordinatorEntity` views (`switch.py`, `number.py`, `binary_sensor.py`, and `GuardStatusSensor` beyond its setup wiring) aren't covered, as they have little logic of their own; extend `conftest.py`'s stubs (`restore_state`, number/switch/binary_sensor bases) if that changes.

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

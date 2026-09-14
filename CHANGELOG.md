# Changelog

All notable changes to this project will be documented in this file.

---

## [v0.0.3] - 2026-09-14

### Features
* feat: enhance functionality with run limit and cooldown features, including heartbeat management and diagnostics updates

## [v0.0.2] - 2026-09-12

### Bug Fixes
* fix: update integration type from helper to device in manifest

## [v0.0.1] - 2026-09-12

### Features
* feat: simplify unique ID generation and add native step to number entities.
* feat: Add device information to number entity.
* feat: Add sensor and binary sensor platforms and refactor existing entities to utilize a new data coordinator.
* feat: add options flow for component configuration and remove heartbeat number entity.
* feat: allow heartbeat interval configuration in options flow.
* feat: Refine config flow to conditionally show device type and heartbeat, and adjust blocking condition log levels from warning to debug.
* feat: remove run limit, cooldown, and heartbeat interval configuration options and their translations

### Bug Fixes
* fix: ensure unique IDs for number entities and remove await from config entry update.

### Refactoring
* Refactor code structure for improved readability and maintainability
* refactor: Update number entities to use `ConfigEntry` type hint, `translation_key` for naming, and keyword arguments for instantiation.
* refactor: Decouple guard switch state from target activation and centralize condition evaluation.
* refactor: Extract configuration schema definition into a reusable helper function.



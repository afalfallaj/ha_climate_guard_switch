## Climate Guard Switch

A "smart proxy" for your climate heater/cooler switch — adds run limits, cooldowns, a heartbeat dead-man's-switch, and environmental gates (sun/weather/thermostat override) on top of a plain `switch.*` entity.

### What it does:
- Wraps an existing hardware `switch.*` entity, so it stays a drop-in `heater`/`cooler` for `generic_thermostat` or `dual_smart_thermostat`
- Enforces a maximum run time and a rest period between runs, to protect equipment (set either to 0 to disable it and rely on your thermostat's own cycling instead)
- Periodically re-pulses the hardware switch while running — this keeps the device's own built-in auto-off timer from tripping during normal use; that timer only becomes the active safety net if Home Assistant itself goes down and the pulses stop
- Optionally only runs when the sun is up, the weather matches an allow-list, or gates on a linked thermostat
- Run limit / cooldown are adjustable instantly from number sliders, no restart needed
- Optional read-only **History view**: combines any temperature sensor, thermostat and heating/cooling entities (from any integration) into Home Assistant's built-in history chart, where each viewer picks their own date range

### Requirements:
- An existing `switch.*` entity to guard (e.g. a Shelly relay driving a water heater or fan) — not needed for a History view
- Home Assistant 2025.8.0 or newer

### Configuration:
Add through **Settings → Devices & Services → Add Integration**, then choose **Guard switch** (pick the target switch and device type) or **History view** (pick the entities to show). Sensors/gates and run-limit/cooldown defaults, and a History view's entities, are all editable afterward from the same integration entry.

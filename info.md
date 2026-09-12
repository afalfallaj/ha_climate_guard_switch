## Climate Guard Switch

A "smart proxy" for your climate heater/cooler switch — adds run limits, cooldowns, a heartbeat dead-man's-switch, and environmental gates (sun/weather/thermostat override) on top of a plain `switch.*` entity.

### What it does:
- Wraps an existing hardware `switch.*` entity, so it stays a drop-in `heater`/`cooler` for `generic_thermostat` or `dual_smart_thermostat`
- Enforces a maximum run time and a rest period between runs, to protect equipment
- Periodically re-pulses the hardware switch while running, so the device's own auto-off timer keeps working as a fallback if Home Assistant goes down
- Optionally only runs when the sun is up, the weather matches an allow-list, or gates on a linked thermostat
- Run limit / cooldown are adjustable instantly from number sliders, no restart needed

### Requirements:
- An existing `switch.*` entity to guard (e.g. a Shelly relay driving a water heater or fan)
- Home Assistant 2025.8.0 or newer

### Configuration:
Add through **Settings → Devices & Services → Add Integration**, picking the target switch and device type. Sensors/gates and run-limit/cooldown defaults are all editable afterward from the same integration entry.

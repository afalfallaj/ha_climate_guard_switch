# Climate Guard Switch

A custom Home Assistant integration acting as a "Smart Proxy" for your climate heater/cooler switches. It adds critical safety and logic layers to standard relay switches (`switch.*`).

## Features

- **🛡️ Safety & Protection**:
  - **Run Limits**: Automatically turns off the device after X minutes to prevent overheating or waste. Set to **0 to disable** — the guard will then never force a stop on its own, and only turns the device off when your thermostat does.
  - **Cooldowns**: Enforces a rest period between runs to protect equipment (compressors) and prevent short-cycling. Set to **0 to disable** — cycling speed is then entirely controlled by your thermostat's own hysteresis/`min_cycle_duration` (this is a normal setup if the thermostat already limits short-cycling and you just want the other safety layers).
  - **Dead Man's Switch (Heartbeat)**: While the device is running, periodically re-sends `turn_on` to the hardware switch (every `heartbeat_interval_seconds`, default 10s). This is what keeps a Shelly/relay's own built-in auto-off timer from ever tripping during normal operation — it's continuously refreshed. The hardware auto-off is only meant to be a backstop for if Home Assistant itself crashes: once HA stops, the pulses stop, and the hardware's own timer becomes the real safety net (requires that auto-off to be configured on the device itself). **This also gates Run Limit**: the run-limit cutoff is checked on each heartbeat tick, so setting Heartbeat to 0 disables Run Limit enforcement too, even if Run Limit itself is set above 0. The Status sensor will call this out in its state text if it applies to your setup.

- **☀️ Environmental Gates**:
  - **Sun Check**: Only run when the sun is up (configurable).
  - **Weather Check**: Only run during specific weather conditions (e.g., "Sunny", "Partly Cloudy").

- **🌡️ Thermostat Integration**:
  - **Linked Override**: Link your thermostat (`climate.*`). If you manually change the target temperature, the switch momentarily bypasses the Cooldown to give you immediate heat/cool.

- **📱 Dynamic Control**:
  - Adjust **Run Limits** and **Cooldowns** instantly via dashboard sliders without restarting HA.

## Installation

### Via HACS (Recommended)
1.  Open HACS > Integrations > Menu > Custom Repositories.
2.  Add this repository URL.
3.  Search for "Climate Guard Switch" and install.
4.  Restart Home Assistant.

### Manual
1.  Copy the `custom_components/climate_guard_switch` folder to your `config/custom_components/` directory.
2.  Restart Home Assistant.

## Configuration

1.  Go to **Settings > Devices & Services > Add Integration**.
2.  Search for **"Climate Guard Switch"**.
3.  Choose **Guard switch** (protects a heater/cooler relay) or **History view** (a read-only combined history chart, see [History view](#history-view-optional)).
4.  For a guard switch, follow the setup wizard:
    - **Target Entity**: The physical switch (e.g., `switch.shelly_water_heater`).
    - **Device Type**: Heater or Cooler (affects icons).
    - **Linked Thermostat**: (Optional) For manual overrides.
    - **Gates**: Select allowed Weather states or Sun requirements.
    - **Limits**: Set your defaults.

## Usage

This integration creates a **Device** with:
- **Switch**: The main control entity. usage this in your `generic_thermostat` or `dual_smart_thermostat`.
- **Number Entities**: Sliders to adjust limits on the fly.

### Example YAML for Thermostat
```yaml
climate:
  - platform: dual_smart_thermostat
    name: Climate System
    heater: switch.climate_guard_heater  # <--- The Proxy Switch
    cooler: switch.climate_guard_cooler  # <--- The Proxy Switch
    target_sensor: sensor.water_tank_temp
```

## History view (optional)

Home Assistant's built-in **History** page draws one combined chart for a thermostat: the current temperature, the target temperature, and shaded heating/cooling periods. A **History view** builds that same chart from entities of *any* integration, so everything is in one place, and **each person picks their own date range** (24 hours, 7 days, a year...) without changing anything for anyone else.

It is **read-only**: no controls, and it never switches anything. It is separate from the guard switch, so existing guards are unaffected, and you can add several views (for example one for the water heater and one for a room).

### Set it up
1.  **Settings > Devices & Services > Add Integration > Climate Guard Switch**, then choose **History view**.
2.  Pick the entities. They can come from any integration, and you can change them later with **Configure**:
    - **Temperature sensor** (required): the temperature line. Heating and cooling are shaded under it.
    - **Thermostat** (optional): adds the target temperature line.
    - **Heating** / **Cooling** (optional): a `switch`, `binary_sensor` or `input_boolean`. Pick the physical relay (for example a Shelly switch), so the shading shows what actually ran and not what was requested.

The device gets a read-only **climate** entity (the combined chart) and, for each optional input, a sensor: **Target temperature**, **Heating** and **Cooling** (0 or 100 %).

### View it
Open **History** in the sidebar, choose the device and set any date range. The range is kept in the page address, so it is yours alone and you can bookmark it.

Choosing the device also adds its sensors, which appear as extra charts under the combined one. Pick just the climate entity if you only want the combined chart, or click a name in the legend to hide it.

### How far back can I go?
Home Assistant keeps two kinds of history:

| | What it is | How long |
|---|---|---|
| **Raw history** | Every change. Draws the shaded chart. | Only `purge_keep_days` (**10 days by default**) |
| **Long-term statistics** | One value per hour for sensors. | **Forever** |

- **Any date range** works through long-term statistics: the **Target temperature**, **Heating** and **Cooling** sensors of this device (Heating 35 % means the heating ran about 35 % of that hour). Add your temperature sensor to the History selection too if you want its temperature line for old dates (it has its own long-term statistics if it has a state class).
- The **shaded combined chart** only reaches back as far as raw history. To keep more, raise the recorder setting in `configuration.yaml`:
  ```yaml
  recorder:
    purge_keep_days: 365
  ```
  This applies to *every* entity, so the database grows and long ranges load more slowly. Use `recorder: exclude:` for entities you don't need history for.
- **History starts when the device is added.** Nothing is backfilled, so a year of history exists only after a year.

### Good to know
- Home Assistant may expose new climate entities to voice assistants by default. The History view can't be controlled (changing its mode is rejected), but you can un-expose it under **Settings > Voice assistants > Expose**.
- The chart shows what your relays did. The guard switch's own *Active* sensor can lag a run-limit stop, so prefer the physical relay as the heating/cooling input.
- If you remove an input in **Configure**, its sensor stops updating and stays as *unavailable*. Delete it under **Settings > Devices & Services > Entities**.
- After copying the files in, do a full Home Assistant restart: a reload is not enough for the new climate platform.

## Disclaimer

*USE AT YOUR OWN RISK* This project is a personal hobby project provided for experimental purposes only. Its code is written and maintained with AI assistance rather than by hand line-by-line; it's reviewed before merging, but you should still read the source and test thoroughly in your own environment before controlling real heating/cooling hardware with it.

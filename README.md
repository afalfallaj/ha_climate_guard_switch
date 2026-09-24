# Climate Guard Switch

A custom Home Assistant integration acting as a "Smart Proxy" for your climate heater/cooler switches. It adds critical safety and logic layers to standard relay switches (`switch.*`).

## Features

- **🛡️ Safety & Protection**:
  - **Run Limits**: Automatically turns off the device after X minutes to prevent overheating or waste. Set to **0 to disable** — the guard will then never force a stop on its own, and only turns the device off when your thermostat does.
  - **Cooldowns**: Enforces a rest period between runs to protect equipment (compressors) and prevent short-cycling. Set to **0 to disable** — cycling speed is then entirely controlled by your thermostat's own hysteresis/`min_cycle_duration` (this is a normal setup if the thermostat already limits short-cycling and you just want the other safety layers).
  - **Dead Man's Switch (Heartbeat)**: While the device is running, periodically re-sends `turn_on` to the hardware switch (every `heartbeat_interval_seconds`, default 10s). This is what keeps a relay's own built-in auto-off timer from ever tripping during normal operation — it's continuously refreshed. The hardware auto-off is only meant to be a backstop for if Home Assistant itself crashes: once HA stops, the pulses stop, and the hardware's own timer becomes the real safety net (requires that auto-off to be configured on the device itself). **This also gates Run Limit**: the run-limit cutoff is checked on each heartbeat tick, so setting Heartbeat to 0 disables Run Limit enforcement too, even if Run Limit itself is set above 0. The Status sensor will call this out in its state text if it applies to your setup.

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
    - **Target Entity**: The physical switch (e.g., `switch.heater_relay`).
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
    target_sensor: sensor.room_temperature
```

## History view (optional)

Home Assistant's built-in **History** page draws one combined chart for a thermostat: the current temperature, the target temperature, and shaded heating/cooling periods. A **History view** builds that same chart from entities of *any* integration, so everything is in one place, and **each person picks their own date range** (24 hours, 7 days, a year...) without changing anything for anyone else.

It is **read-only**: no controls, and it never switches anything. It is separate from the guard switch, so existing guards are unaffected, and you can add several views (for example one per room).

### Set it up
1.  **Settings > Devices & Services > Add Integration > Climate Guard Switch**, then choose **History view**.
2.  Pick the entities. They can come from any integration, and you can change them later with **Configure**:
    - **Temperature sensor** (required): the temperature line. Heating and cooling are shaded under it.
    - **Thermostat** (optional): adds the target temperature line.
    - **Heating** / **Cooling** (optional): a `switch`, `binary_sensor` or `input_boolean`. Pick the physical relay, so the shading shows what actually ran and not what was requested.

The device gets a read-only **climate** entity (the combined chart) and, for each optional input, sensors: **Target temperature**, **Heating** and **Cooling** (0 or 100 %, hidden by default), and **Temperature while heating** / **Temperature while cooling** (hidden by default, see [below](#heating-and-cooling-in-the-same-graph-for-any-date-range)).

### View it
Open **History** in the sidebar, choose the device and set any date range. The range is kept in the page address, so it is yours alone and you can bookmark it.

Picking the device shows the climate entity and the Target temperature; the other sensors are hidden by default and can be added by name, or un-hidden under **Settings > Devices & services > Entities**.

### Heating and cooling in the same graph, for any date range

Home Assistant draws values of one kind per chart and keeps long-term statistics only for sensors, so a relay's on/off can never join the temperature chart for old dates. The History view works around this with two more sensors, **Temperature while heating** and **Temperature while cooling**: each carries the temperature only while that input is on, and is empty otherwise. Drawn in red and blue on top of the temperature they mark the heating and cooling periods in the same graph, and because they are temperature sensors they have long-term statistics, so this works for any date range.

They are hidden by default (list them in cards by name; they are not meant for device picks) and marked diagnostic (not exposed to voice assistants). The **Temperature traces** option in **Configure** turns them off. Entity ids follow the view name; the examples use a view called "Climate History" and a temperature sensor `sensor.room_temperature`.

Recent days (raw history):
```yaml
type: history-graph
title: Climate
hours_to_show: 72
entities:
  - entity: sensor.room_temperature
    name: Temperature
  - entity: sensor.climate_history_target_temperature
    name: Target
  - entity: sensor.climate_history_temperature_while_heating   # traces last, so they draw on top
    name: Heating
    color: red
  - entity: sensor.climate_history_temperature_while_cooling
    name: Cooling
    color: blue
```

Any date range (long-term statistics):
```yaml
type: statistics-graph
title: Climate - 30 days
days_to_show: 30
period: hour          # keep "hour": with day or month the marks join across idle days
stat_types: mean
chart_type: line
entities:
  - entity: sensor.room_temperature
    name: Temperature
  - entity: sensor.climate_history_target_temperature
    name: Target
  - entity: sensor.climate_history_temperature_while_heating
    name: Heating
    color: red
  - entity: sensor.climate_history_temperature_while_cooling
    name: Cooling
    color: blue
```

Each viewer picks their own range: put a date picker above the card and let the card follow it. The picker is the Energy dashboard's, but it needs no energy setup (the `energy` integration is part of `default_config`):
```yaml
type: vertical-stack
cards:
  - type: energy-date-selection
    collection_key: energy_climate_history
  - type: statistics-graph
    title: Climate
    energy_date_selection: true
    collection_key: energy_climate_history
    period: hour
    stat_types: mean
    chart_type: line
    entities:
      - entity: sensor.room_temperature
        name: Temperature
      - entity: sensor.climate_history_target_temperature
        name: Target
      - entity: sensor.climate_history_temperature_while_heating
        name: Heating
        color: red
      - entity: sensor.climate_history_temperature_while_cooling
        name: Cooling
        color: blue
```

Good to know:
- Over a whole year the red and blue marks show *when* heating and cooling happened, not how much. Use a shorter range for detail.
- Keep `period: hour`. With `day` or `month` the marks join into continuous lines across idle days.
- On the History page, the older (statistics) part joins the marks across idle hours. That is why these sensors are hidden from device picks; the cards above are the intended way to view them.
- Hourly values are slightly approximate at the edges of a run: the last reading is carried at most to the end of its 5-minute bucket.
- Checked against Home Assistant 2026.9.3; the built-in cards may change.

### How far back can I go?
Home Assistant keeps two kinds of history:

| | What it is | How long |
|---|---|---|
| **Raw history** | Every change. Draws the shaded chart. | Only `purge_keep_days` (**10 days by default**) |
| **Long-term statistics** | One value per hour for sensors. | **Forever** |

- **Any date range** works through long-term statistics: the **Target temperature**, **Heating** and **Cooling** sensors of this device (Heating 35 % means the heating ran about 35 % of that hour), and the **Temperature while heating / cooling** sensors (see above). Add your temperature sensor to the History selection too if you want its temperature line for old dates (it has its own long-term statistics if it has a state class).
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

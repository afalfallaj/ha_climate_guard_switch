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
3.  Follow the setup wizard:
    - **Target Entity**: The physical switch (e.g., `switch.heater_relay`).
    - **Device Type**: Heater or Cooler (affects icons).
    - **Linked Thermostat**: (Optional) For manual overrides, and the Target temperature sensor for history charts.
    - **Temperature Sensor**: (Optional) For history charts, see [History charts](#history-charts-optional).
    - **Gates**: Select allowed Weather states or Sun requirements.
    - **Limits**: Set your defaults.

## Usage

This integration creates a **Device** with:
- **Switch**: The main control entity. usage this in your `generic_thermostat` or `dual_smart_thermostat`.
- **Number Entities**: Sliders to adjust limits on the fly.
- **History chart sensors**: Target temperature and Temperature while heating/cooling, see [History charts](#history-charts-optional).

### Example YAML for Thermostat
```yaml
climate:
  - platform: dual_smart_thermostat
    name: Climate System
    heater: switch.climate_guard_heater  # <--- The Proxy Switch
    cooler: switch.climate_guard_cooler  # <--- The Proxy Switch
    target_sensor: sensor.room_temperature
```

## History charts (optional)

Each guard device also offers read-only sensors that let Home Assistant's *built-in* cards show the temperature, its target and the heating/cooling periods **together in one chart, for any date range**, with each viewer choosing their own range.

### Why they exist
Home Assistant draws values of one kind per chart and keeps long-term statistics only for sensors. A relay's on/off can never share a chart with a temperature, and beyond the raw history (10 days by default) it cannot be drawn at all. So the guard publishes the pieces as temperature sensors:

| Sensor | Value |
|---|---|
| **Target temperature** | the linked thermostat's target (needs a linked thermostat) |
| **Temperature while heating** (heater guards) / **Temperature while cooling** (cooler guards) | the temperature, but only while the guarded relay is on; empty otherwise |

Drawn in red and blue on top of the temperature, the "while" sensors mark the heating and cooling periods. Because they are temperature sensors they have long-term statistics, so this works for any range.

### Set it up
- **Temperature Sensor** (optional, in the guard's setup or **Configure**): the temperature the marks are drawn on. If empty, the linked thermostat's current temperature is used. With neither, there is no "while" sensor.
- The sensors follow the physical relay, so they show what actually ran.
- A heater guard and a cooler guard that share one thermostat both get a Target temperature sensor; chart one of them (and disable the other if it bothers you).
- Upgrading from v0.0.4 to v0.0.6: the separate "History view" entries are no longer supported and show a message asking you to delete them. The same sensors now live on your guard devices, under new entity ids.

### Show it
Entity ids follow the guard names. The examples use guards called "Heater Guard" and "Cooler Guard" and a temperature sensor `sensor.room_temperature`.

Recent days (raw history):
```yaml
type: history-graph
title: Climate
hours_to_show: 72
entities:
  - entity: sensor.room_temperature
    name: Temperature
    color: white      # suits a dark theme; pick any CSS color
  - entity: sensor.heater_guard_target_temperature
    name: Target
    color: orange
  - entity: sensor.heater_guard_temperature_while_heating   # traces last, so they draw on top
    name: Heating
    color: red
  - entity: sensor.cooler_guard_temperature_while_cooling
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
    color: white      # suits a dark theme; pick any CSS color
  - entity: sensor.heater_guard_target_temperature
    name: Target
    color: orange
  - entity: sensor.heater_guard_temperature_while_heating
    name: Heating
    color: red
  - entity: sensor.cooler_guard_temperature_while_cooling
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
        color: white
      - entity: sensor.heater_guard_target_temperature
        name: Target
        color: orange
      - entity: sensor.heater_guard_temperature_while_heating
        name: Heating
        color: red
      - entity: sensor.cooler_guard_temperature_while_cooling
        name: Cooling
        color: blue
```

### Good to know
- History starts when the sensors exist; nothing is backfilled.
- The `history-graph` card uses raw history, which the recorder keeps for `purge_keep_days` (10 by default). The `statistics-graph` card is not limited.
- Over a whole year the red and blue marks show *when* heating and cooling happened, not how much. Use a shorter range for detail.
- Keep `period: hour`. With `day` or `month` the marks join into continuous lines across idle days.
- On the History page (for example when you pick the whole device), the older statistics part joins the marks across idle hours. Use the cards above for long ranges.
- Hourly values are slightly approximate at the edges of a run: the last reading is carried at most to the end of its 5-minute bucket.
- After copying the files in, do a full Home Assistant restart.
- Checked against Home Assistant 2026.9.3; the built-in cards may change.

## Disclaimer

*USE AT YOUR OWN RISK* This project is a personal hobby project provided for experimental purposes only. Its code is written and maintained with AI assistance rather than by hand line-by-line; it's reviewed before merging, but you should still read the source and test thoroughly in your own environment before controlling real heating/cooling hardware with it.

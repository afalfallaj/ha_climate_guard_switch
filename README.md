# Climate Guard Switch

A custom Home Assistant integration acting as a "Smart Proxy" for your climate heater/cooler switches. It adds critical safety and logic layers to standard relay switches (`switch.*`).

## Features

- **🛡️ Safety & Protection**:
  - **Run Limits**: Automatically turns off the device after X minutes to prevent overheating or waste.
  - **Cooldowns**: Enforces a rest period between runs to protect equipment (compressors) and prevent short-cycling.
  - **Dead Man's Switch (Heartbeat)**: Periodically pulses the hardware switch. If Home Assistant crashes, the hardware's own auto-off timer takes over (requires hardware config).

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

## Disclaimer

*USE AT YOUR OWN RISK* This project is a personal hobby project provided for experimental purposes only. 

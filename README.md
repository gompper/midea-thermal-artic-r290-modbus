# Midea Heat Pump Modbus Integration for Home Assistant

Home Assistant integration for Midea M-Thermal Arctic R290 heat pumps via Modbus RTU over TCP.

Built on the shared Modbus connections introduced in Home Assistant 2026.9: the integration is set up in the UI, knows the heat pump's register map itself, and shares its gateway connection with any other Modbus integration on the same bus instead of competing with it. No `modbus:` YAML is needed.

![Home Assistant Dashboard](resources/home-assistant-dashboard.png)

## Hardware Setup

- **Heat Pump**: Midea Thermal Arctic R290 10kW
- **Modbus Gateway**: Elfin EW11-A (WiFi to RS-485 converter)
- **Home Assistant**: Running on Raspberry Pi 5 (Docker)

### Wiring

```
Heat Pump (Wired Controller) → EW11-A → WiFi (AP: leni) → Raspberry Pi → Home Assistant
         H1 (-) → A                      10.10.100.131       10.10.100.1      Modbus TCP
         H2 (+) → B
```

The Pi runs its own isolated WiFi AP ("leni", 10.10.100.x) on a dedicated USB WiFi dongle with external antenna. The EW11-A connects to it as a client — it is not on the home network. The Pi connects to the home router via ethernet.

### EW11-A Configuration

- **Mode**: Modbus TCP to RTU gateway (NOT transparent TCP)
- **Baud Rate**: 9600
- **Data Bits**: 8
- **Parity**: None
- **Stop Bits**: 1
- **TCP Port**: 8899
- **WiFi**: STA mode, connects to Pi AP "leni"

For full EW11-A settings see:
- [Current STA mode settings](resources/ew11-sta-settings.md)
- [AP mode settings (alternative)](resources/ew11-ap-settings.md)

To access the EW11-A web UI from your PC, tunnel through the Pi:
```bash
ssh -L 8080:10.10.100.131:80 -f -N <user>@<pi-ip>
```
Then open http://localhost:8080.

### Modbus Settings

- **Slave Address**: Default is 1, this project uses 2 (configurable in HMI wired controller)
- **Protocol**: Modbus RTU

## Files

| File | Description |
|------|-------------|
| `custom_components/midea_m_thermal/` | The integration (requires Home Assistant 2026.9 or later) |
| `custom_components/midea_m_thermal/m_thermal_modbus/` | Device library: the register map on [modbus-connection](https://home-assistant-libs.github.io/modbus-connection/), no Home Assistant imports |
| `heat_pump_package.yaml` | Optional HA package: daily/monthly/yearly energy meters and a zone 1 activity sensor |
| `heat_pump_dashboard.yaml` | Optional Lovelace dashboard for heat pump monitoring |
| `configuration.yaml` | This project's HA config, which includes the package and dashboard |
| `tests/` | Tests against Home Assistant 2026.9.3 and a mock heat pump loaded with a real register dump |
| `scan_registers.py`* | Modbus register scanner with full documentation |
| `register_dump.txt`* | Complete register dump with values and descriptions |
| `deprecated/`* | Archived ESP32/ESPHome prototype from before the EW11-A; not active |

*Utility/reference files - not needed for running.

## Home Assistant on Raspberry Pi

### Option A: Home Assistant OS (recommended for beginners)

The easiest way. Flash a ready-made image to your Pi's SD card:

1. Download the HA OS image for your Pi from https://www.home-assistant.io/installation/raspberrypi
2. Flash it to an SD card using [Balena Etcher](https://etcher.balena.io/) or Raspberry Pi Imager
3. Boot the Pi, then open `http://homeassistant.local:8123`

HA OS gives you automatic updates, the Add-on store, and backups out of the box. The downside is you can't run other software on the Pi - it's dedicated to Home Assistant.

Config directory: `/config/`

### Option B: Docker container (this project's setup)

More flexible - run HA alongside other software. Works on Raspberry Pi OS Lite (headless Debian, no desktop needed). All commands below are run on the Pi via SSH (`ssh user@<pi-ip>`).

Install Docker:

```bash
# Download and run Docker's official install script
curl -fsSL https://get.docker.com | sh

# Allow your user to run docker commands without sudo
sudo usermod -aG docker $USER
```

Log out and back in (or `newgrp docker`) for the group change to take effect.

Start the Home Assistant container:

```bash
# Create the config directory
sudo mkdir -p /root/homeassistant/config

# Start HA container
sudo docker run -d \
  --name home-assistant \
  --restart unless-stopped \       # auto-restart after power loss / reboot
  -v /root/homeassistant/config:/config \  # HA config stored on Pi's filesystem
  -v /etc/localtime:/etc/localtime:ro \    # sync timezone with Pi
  --network host \                 # use Pi's network directly (no port mapping needed)
  ghcr.io/home-assistant/home-assistant:stable
```

Home Assistant is now available at `http://<pi-ip>:8123`.

Useful commands:

```bash
sudo docker restart home-assistant  # restart after config changes
sudo docker logs home-assistant     # view HA logs
sudo docker ps                      # check if container is running
```

Config directory: `/root/homeassistant/config/`

## Installation

Requires Home Assistant 2026.9 or later.

1. Install the integration, either:
   - **HACS**: add this repository as a custom repository (type *Integration*), then download *Midea M-Thermal*, or
   - **Manually**: copy `custom_components/midea_m_thermal/` into your config directory's `custom_components/` (`./upload_integration.sh` does this for the Pi in this project).
2. Restart Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration → Midea M-Thermal** and enter:
   - **Host**: the EW11-A's address (this project: `10.10.100.131`)
   - **Port**: `8899`
   - **Unit ID**: the Modbus address set on the wired controller (Midea default `1`; this project uses `2`)

   The flow reads the heat pump before it saves anything, so a wrong address or unit ID is reported right away.
4. Optional: add `heat_pump_package.yaml` as a package and `heat_pump_dashboard.yaml` as a YAML dashboard (see `configuration.yaml`). The dashboard's charts use [apexcharts-card](https://github.com/RomRider/apexcharts-card) from HACS.

The gateway, port or unit ID can be changed later with **Reconfigure** on the integration's entry.

### Migrating from the YAML setup

Earlier versions of this repository configured the heat pump through a `modbus:` hub in `configuration.yaml`. Remove that hub, the `HP …` template sensors and select, and the `shell_command`/automations/`input_number` of the old `heat_pump_package_target_control.yaml` before adding the integration, so only one client polls the gateway. Entity IDs change from `…hp_…` to `…heat_pump_…`; the shipped dashboard and package already use the new ones.

## Features

- Real-time monitoring: temperatures, pressures, compressor frequency, flow, power, heating capacity, COP
- Power on/off (register 0, Zone 1 water bit only, so other zones keep their state)
- Mode: Auto / Cooling / Heating (register 1)
- Target temperature whose min/max follow the active mode, read from the heat pump's own limits (registers 201-204; Cooling 5-25 °C, Heating 25-55 °C on this unit). Switching to cooling with a heating setpoint above the cooling maximum pulls the setpoint down, and every write is clamped to the live mode as a safety net
- Lifetime energy counter that holds its value while the heat pump is offline, so long-term statistics and the Energy dashboard stay intact
- Diagnostics download with the raw register map
- Two Modbus requests per 30 s poll (registers 0-2 and 100-199), where the YAML setup made one per sensor

## Register Documentation

### Registers Used

| Address | Name | Description |
|--------:|:-----|:------------|
|       0 | Power on/off | Bit field: Bit1=Zone1 water (0b0010=2 for Zone1-only), 0=off |
|       1 | Mode setting | 1=Auto, 2=Cooling, 3=Heating |
|       2 | Set water temp T1s | Zone1 target (low byte), Zone2 (high byte). Same register for both modes — only the valid range differs (see below) |
|      16 | Power Zone 1 | Zone1 water temp subsystem switch (reg 0 is the real power control) |
|     201 | T1s cooling upper limit | Max valid target in Cooling mode (e.g. 25°C) |
|     202 | T1s cooling lower limit | Min valid target in Cooling mode (e.g. 5°C) |
|     203 | T1s heating upper limit | Max valid target in Heating mode (e.g. 55°C) |
|     204 | T1s heating lower limit | Min valid target in Heating mode (e.g. 25°C) |
|     100 | Compressor frequency | Current frequency in Hz, 0=off |
|     101 | Operating state | 0=off, 2=cooling active, 3=heating active |
|     104 | Tw_in | Water inlet (return) temperature |
|     105 | Tw_out | Water outlet (supply) temperature |
|     106 | T3 | Condenser refrigerant temperature |
|     107 | T4 | Outdoor ambient temperature |
|     108 | Tp | Compressor discharge (hot gas) temperature |
|     109 | Th | Compressor suction temperature |
|     110 | T1 | Total outlet water temperature |
|     116 | P1 | High-side refrigerant pressure (kPa) |
|     117 | P2 | Low-side refrigerant pressure (kPa) |
|     118 | ODU current | Outdoor unit current (A) |
|     119 | ODU voltage | Outdoor unit supply voltage (V) |
|     123 | Unit capacity | Nominal capacity in kW (e.g. 10) |
|     124 | Current error | Error code, 0=no error |
|     138 | Water flow | Flow rate through heat exchanger (x0.01 m³/h) |
|     143 | Energy consumption high | Cumulative kWh, high 16 bits (x0.01) |
|     144 | Energy consumption low | Cumulative kWh, low 16 bits (x0.01) |
|     148 | Heating capacity | Real-time heating capacity (x0.01 kW) |
|     150 | Heating power | Real-time power consumption (x0.01 kW). On this unit, reads 0 continuously while in Cooling mode even with the compressor running — appears to be a firmware limitation specific to cooling. Works correctly in Heating mode |
|     151 | Heating COP | Real-time coefficient of performance (x0.01) |
|     199 | Operation mode | 0=Off, 2=Cool, 3=Heat, 5=DHW |

For the full register map (290 registers), see [register_dump.txt](register_dump.txt) or run:

```bash
python scan_registers.py
```

## Notes

- Bulk reads work for registers 0-22 and 100-199, but registers 200-290 must be read individually
- Negative temperatures use 16-bit two's complement (e.g., 65531 = -5°C)
- 32-bit values split across two registers: `(high * 65536 + low) / 100`

## References

- [Midea Modbus Protocol Documentation](resources/midea-modbus-protocol.pdf)
- [Elfin EW11 User Manual](resources/elfin-ew11-user-manual.pdf)

## License

MIT

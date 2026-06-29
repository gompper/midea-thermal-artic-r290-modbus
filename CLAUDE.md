# Midea Modbus Integration Project

## Goal
Integrate Midea Thermal Arctic R290 10kW heat pump with Home Assistant via Modbus RTU.

## Hardware Setup
- **Heat Pump**: Midea Thermal Arctic R290 10kW
- **Home Assistant**: Running on Raspberry Pi 5 (Docker image)
- **Modbus Gateway**: Elfin EW11-A (WiFi to RS-485 converter)

### Architecture
```
Heat Pump (RS-485 H1/H2) → EW11-A → WiFi (AP: leni) → Pi wlx24ec99bfdf3f → Pi eth0 → FritzBox
                                      10.10.100.131        10.10.100.1          192.168.178.107
```
Pi runs an isolated AP ("leni", 10.10.100.x) on `wlx24ec99bfdf3f` (USB WiFi dongle with external antenna). EW11-A connects as STA client.
Pi is on ethernet to FritzBox for Home Assistant traffic.

**Note on AP interface**: Originally on `wlan0` (built-in WiFi). After installing an M.2 HAT + SSD, the HAT's PCB shielded the built-in antenna enough to drop the already-marginal EW11 signal. Moved to the USB dongle (`wlx24ec99bfdf3f`) which has an external antenna and maintains reliable coverage despite lower raw TX power (20 dBm vs 31 dBm). If the USB dongle is removed or replaced, the AP will fail — `wlan0` will not take over automatically.



### EW11-A to Wired Controller Wiring
- EW11-A A (+) → H1
- EW11-A B (-) → H2
- No ground connection needed (short cable)
- Connected to wired controller, NOT outdoor unit

### EW11-A Configuration
- Baud Rate: 9600
- Data Bits: 8
- Parity: None
- Stop Bits: 1
- Mode: Modbus TCP to RTU gateway (must be "Modbus" mode, not transparent TCP)
- WiFi: STA mode, connects to Pi AP "leni", gets IP 10.10.100.131 via DHCP reservation
- Pi AP must use WPA2 (proto: rsn, ccmp) — EW11 will not connect to WPA1/TKIP
- CLI escape (`+++`): disabled (unnecessary attack surface)
- Full settings: [Current STA settings](resources/ew11-sta-settings.md) | [AP mode (alternative)](resources/ew11-ap-settings.md)

#### Accessing EW11-A Web UI
EW11-A is on the isolated 10.10.100.x network — only reachable via SSH tunnel through the Pi:
```bash
ssh -L 8080:10.10.100.131:80 -f -N makro@192.168.178.107
```
Then open http://localhost:8080 (credentials in `secrets.md`)

#### Factory Reset
Hold reset button ~5 seconds → restores AP mode with default IP 10.10.100.254, login admin/admin.
After reset, reconfigure STA mode to connect to "leni" and restore settings per [ew11-sta-settings.md](resources/ew11-sta-settings.md).

#### Pi AP Troubleshooting
If EW11 cycles connecting/disconnecting every ~4 seconds despite correct password:
- Check that standalone `hostapd` is not running alongside NetworkManager: `sudo systemctl status hostapd`
- If running, stop and disable it: `sudo systemctl stop hostapd && sudo systemctl disable hostapd`
- NM manages the AP via the `leni-ap` connection — a second hostapd instance causes a split-brain conflict that kicks clients every 4 seconds.

If EW11 cannot connect at all (no DHCP lease in `sudo journalctl -u NetworkManager`):
- Verify the `leni-ap` connection is active on `wlx24ec99bfdf3f`: `nmcli connection show leni-ap | grep DEVICES`
- If active on `wlan0` instead (e.g. after a re-image or NM reset), move it back: `sudo nmcli connection modify leni-ap connection.interface-name wlx24ec99bfdf3f && sudo nmcli connection down leni-ap && sudo nmcli connection up leni-ap`
- Check signal from the Pi using the now-free `wlan0`: `sudo iw dev wlan0 scan | grep -A3 leni`

### Home Assistant Configuration
- **Pi IP**: 192.168.178.107 (user: makro)
- **EW11-A IP**: 10.10.100.131 (reserved via DHCP on Pi AP), TCP port 8899
- **Modbus slave address**: 2 (default on Midea pumps is 1)
- Config file: `/root/homeassistant/config/configuration.yaml`
- Docker container: `home-assistant`
- Docker image: `ghcr.io/home-assistant/home-assistant:stable`
- HA version: 2026.4.4
- Backup: `/home/makro/ha_backup/ha-backup.sh`, daily 3am, uploads to `pcloud:backup/homeassistant`, 30-day retention
- Pi eth0 on FritzBox LAN (ethernet), `wlx24ec99bfdf3f` (USB dongle, external antenna) as AP "leni" (isolated 10.10.100.x network)
- EW11-A DHCP reservation: MAC `74:e9:d8:7f:71:1c` → `10.10.100.131` (in `/etc/NetworkManager/dnsmasq-shared.d/ew11-reservation.conf`)
- Pi AP config: NetworkManager connection "leni-ap" bound to `wlx24ec99bfdf3f`; reconfigure with `sudo nmcli connection modify leni-ap connection.interface-name wlx24ec99bfdf3f`

### System Configuration
- Zone 1 only (no Zone 2)
- No DHW (domestic hot water)
- No TBH (tank booster heater)
- No IBH (inline booster heater)

## Modbus Specifications
- **Port**: RS-485 (H1"-", H2"+")
- **Baud Rate**: 9600
- **Data Bits**: 8
- **Parity**: None
- **Stop Bits**: 1
- **Protocol**: Modbus RTU (ASCII not supported)
- **Function Codes**: 03H (read), 06H (write single), 10H (write multiple)

### Register Map
| Range | Content | Access | Bulk Read |
|-------|---------|--------|-----------|
| 0-22 | Control registers | R/W | Works |
| 23-99 | Not implemented (gap) | - | - |
| 100-199 | Operating parameters | R | Works |
| 200-290 | Configuration parameters | R/W (209+ writable) | FAILS, read individually |

### Value Encoding
- Some registers pack two values: Zone1 in low 8 bits, Zone2 in high 8 bits
- Negative temperatures: 16-bit two's complement (e.g., 65531 = -5°C)
- 32-bit values: split across two registers, `(high * 65536 + low) / 100`
- 65535 (0xFFFF) and 255 (0xFF) = "not available" or "no sensor"

## Reference Documentation
- `resources/midea-modbus-protocol.pdf` - Modbus mapping table
- `resources/elfin-ew11-user-manual.pdf` - EW11-A user manual
- `register_dump.txt` - Complete register dump with values and descriptions
- `scan_registers.py` - Register scanner with full documentation per register

## Project Files
- `configuration.yaml` - HA config: modbus sensors, template sensors, utility meters, switch
- `heat_pump_dashboard.yaml` - HA dashboard (lovelace, YAML mode)
- `heat_pump_package_target_control.yaml` - HA package: target temp input, automations, shell command
- `set_target.py` - Python script to write target temp to heat pump via Modbus; clamps the value into the active mode's valid range (reads reg 1) before writing
- `scan_registers.py` - Modbus register scanner with detailed descriptions
- `register_dump.txt` - Complete register dump output
- `upload_dashboard.sh` - Upload dashboard to Pi (no restart needed)
- `upload_config.sh` - Upload config to Pi (restart required)
- `upload_package.sh` - Upload package to Pi (restart required)
- `deprecated/` - Archived ESP32/ESPHome approach from before the EW11-A was purchased; not active

## Key Registers

### Control Registers (Read/Write)
| Address | PLC | Description | Values |
|---------|-----|-------------|--------|
| 0 | 40001 | Power on/off | Bit field: Bit0=Zone1/2 room, Bit1=Zone1 water, Bit2=DHW, Bit3=Zone2 water. Zone1 water only = 2 |
| 1 | 40002 | Mode setting | 1=Auto, 2=Cooling, 3=Heating |
| 2 | 40003 | Set water temp T1s | Zone1 (low 8 bits), Zone2 (high 8 bits) |
| 11 | 40012 | T1s Zone 1 | Water temp setpoint (preferred over reg 2) |
| 16 | 40017 | Power Zone 1 | Zone1 water temp control subsystem only — reg 0 is the real power switch |

### Setpoint Limits (Read Only, mode-dependent)
| Address | PLC | Description | Zone1 value |
|---------|-----|-------------|--------|
| 201 | 40202 | T1s cooling upper limit | 25°C |
| 202 | 40203 | T1s cooling lower limit | 5°C |
| 203 | 40204 | T1s heating upper limit | 55°C |
| 204 | 40205 | T1s heating lower limit | 25°C |

Register 2/11 (T1s) is the *same* setpoint register for both modes — there's no separate "cooling target". Only the valid range differs, enforced above. Writing a value outside the active mode's range is invalid.

### Sensor Registers (Read Only)
| Address | PLC | Description | Unit |
|---------|-----|-------------|------|
| 100 | 40101 | Compressor frequency | Hz |
| 101 | 40102 | Operating state | 0=off, 2=cooling, 3=heating |
| 104 | 40105 | Tw_in (water inlet) | °C |
| 105 | 40106 | Tw_out (water outlet) | °C |
| 107 | 40108 | T4 (outdoor ambient) | °C |
| 108 | 40109 | Discharge temp | °C |
| 109 | 40110 | Suction temp | °C |
| 110 | 40111 | T1 (total outlet water) | °C |
| 116 | 40117 | P1 (high pressure) | kPa |
| 117 | 40118 | P2 (low pressure) | kPa |
| 118 | 40119 | ODU current | A (x0.1) |
| 119 | 40120 | ODU voltage | V |
| 124 | 40125 | Current error | Error code |
| 138 | 40139 | Water flow | m³/h (x0.01) |
| 143-144 | 40144-45 | Energy consumption | kWh (x0.01, 32-bit) |
| 148 | 40149 | Real-time heating capacity | kW (x0.01) |
| 150 | 40151 | Power consumption | kW (x0.01) |
| 151 | 40152 | COP | x0.01 |
| 199 | 40200 | Operation mode | 0=Off, 2=Cooling, 3=Heating, 5=DHW |

**Known issue**: Register 150 (Power consumption) reads 0 continuously while in Cooling mode on this unit, even with the compressor actively running (confirmed live: mode=2, compressor=41Hz, reg150=0). Works correctly in Heating mode. This is a firmware limitation on the heat pump, not an HA config issue — don't try to "fix" it by substituting another register; ODU current × voltage (HP ODU Power) is the only reliable live power figure while cooling, though it excludes the water pump.

### Template Sensors & Controls
- **HP Mode** - Mode picker (Auto/Cooling/Heating) as a dashboard tile with tap-buttons (`select-options` feature, not a dropdown), reads reg 1, writes via modbus.write_register
- **HP Mode Text** - Operating mode as text (Off/Cool/Heat/DHW), reads reg 199 (read-only)
- **HP State Text** - Operating state as text (Idle/Cool/Heat)
- **HP Current Target** - Zone 1 target extracted from packed register 2
- **HP Power Consumption** - Power raw / 100 in kW (see register 150 known issue above — reads 0 in Cooling mode)
- **HP ODU Power** - ODU current × voltage in W
- **HP Delta T** - T1 outlet minus Tw_in inlet
- **HP COP Filtered** - COP capped at 10 (raw register gives unrealistic spikes)
- **HP Energy Total** - 32-bit combined energy (regs 143+144), with availability guard

### Energy Tracking
- **HP Energy Total** - Cumulative kWh from Modbus (template sensor, total_increasing)
- **HP Energy Daily/Monthly/Yearly** - Utility meters sourced from HP Energy Total
- Dashboard bars use `statistics-graph` with `stat_types: change` on HP Energy Total

### Target Temperature Control (heat_pump_package_target_control.yaml)
- `input_number.hp_target_temp` — range 5-55°C (union of both modes' valid ranges, see Setpoint Limits above)
- **HP Write Target Temp** — pushes input_number changes to the heat pump via `set_target.py`
- **HP Sync Target Temp** — pulls the real device value back into input_number whenever it changes; also runs on HA start (10s delay) to catch up after a restart
- **HP Clamp Target Temp for Mode** — when mode changes (or on HA start), clamps the displayed target into the active mode's valid range (Cooling 5-25°C, Heating 25-55°C; Auto defaults to the heating range)
- `set_target.py` independently re-clamps every write into the live mode's valid range (reads register 1 itself) before writing register 2 — a hardware-safety net that holds even if the HA-side automations are mid-restart or the UI is set out of range

### Known Gotchas
- **`input_number.set_min_max` does not exist** as a service in this HA version (verified against `/usr/src/homeassistant/homeassistant/components/input_number/__init__.py` — only `set_value`, `increment`, `decrement`, `reload` are registered). Don't use it; min/max for input_number is static config only. This is why the target-temp range is widened statically (5-55) instead of resized per mode.
- **Automation `platform: state` triggers can miss the very first state change of a templated/Modbus-derived entity right after an HA restart** (component load-order race — confirmed via the `events` table: `automation_triggered` events were missing for the very first transition, every time, across multiple restarts). `platform: homeassistant, event: start` reliably fires for this project's package automations; `platform: event, event_type: homeassistant_started` did not in testing, despite supposedly firing later/more completely. Pair boot-time logic with the `start` trigger (+ a short delay if it depends on a fresh Modbus poll), not a bare state trigger.
- **Recorder hides several useful attributes** (`min`/`max` on input_number, `last_triggered` on automations) from history by default in this HA version — querying the SQLite DB for these will silently return nothing useful. Verify automation behavior via the `events` table (`event_types` row for `automation_triggered`, id usually ~27) joined to `event_data`, not via `states`/`state_attributes`.
- **Lovelace dashboard URL paths must contain a hyphen.** The `solakon` dashboard key in `configuration.yaml`'s `lovelace.dashboards` lacked one and crashed the *entire* frontend into recovery mode on restart (unrelated to any heat-pump change — just lurking in the shared file). Fixed by renaming to `solakon-solar`. If a restart ever drops the whole UI into recovery mode, check this first.

## TODO
- [x] Determine RS-485 adapter for Raspberry Pi → EW11-A
- [x] Configure Home Assistant Modbus integration
- [x] Create sensors
- [x] Test communication - working!
- [x] Add power switch and target temperature control
- [x] Create HA dashboard
- [x] Add energy tracking (daily/monthly/yearly)
- [x] Create register scanner with documentation
- [x] Publish on GitHub
- [x] Add mode control (auto/heating/cooling) — enabled cooling via reg 210 bit 9, template select on reg 1
- [x] Harden EW11-A: isolated Pi AP network, disabled CLI escape, restricted web access
- [x] Clamp target temp to the active mode's valid range (Cooling 5-25°C, Heating 25-55°C), restart-safe
- [x] Improve EW11-A WiFi signal — moved "leni" AP to USB WiFi dongle with external antenna after M.2 HAT shielded built-in wlan0 antenna

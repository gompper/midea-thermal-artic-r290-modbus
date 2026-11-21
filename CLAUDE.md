# Midea Modbus Integration Project

## Goal
Integrate Midea Thermal Arctic R290 10kW heat pump with Home Assistant via Modbus RTU, as a UI-configured custom integration (`custom_components/midea_m_thermal`) on HA 2026.9's shared Modbus connections.

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



### Gateway to Wired Controller Wiring
- Gateway A (+) → H1
- Gateway B (-) → H2
- Gateway E/shield → E_H (HA/HB is the link to the hydraulic module, not Modbus)
- Source: wired controller manual MD23IU-047I, chapter 7.3 (H1 = A+, H2 = B−). The older `resources/midea-modbus-protocol.pdf` says "H1 '-', H2 '+'", which is wrong for this controller generation (HMI software V1.0.0.x). Swapped lines don't damage anything; the heat pump just never answers (adapter status: received bytes = 0)
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
- Integration: `/root/homeassistant/config/custom_components/midea_m_thermal/`, added via Settings → Devices & Services (host 10.10.100.131, port 8899, unit ID 2)
- Docker container: `home-assistant`
- Docker image: `ghcr.io/home-assistant/home-assistant:stable`
- HA version: must be 2026.9 or later for the integration (the YAML setup was built on 2026.4.4)
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
- `custom_components/midea_m_thermal/` - The integration: config flow, coordinator, sensor/number/select/switch platforms, diagnostics
- `custom_components/midea_m_thermal/m_thermal_modbus/` - Device library (register map on `modbus-connection`); must stay free of `homeassistant` imports so it can move to PyPI
- `tests/` - pytest suite against HA 2026.9.3 + the `modbus-connection` mock, seeded from `tests/fixtures/registers.json` (the real `register_dump.txt` values)
- `heat_pump_package.yaml` - HA package: utility meters + zone 1 activity template (everything else is native to the integration)
- `heat_pump_dashboard.yaml` - HA dashboard (lovelace, YAML mode); `tests/test_dashboard.py` fails if it references an entity the setup doesn't create
- `configuration.yaml` - This project's HA config (includes the package and dashboards; no `modbus:` hub)
- `scan_registers.py` - Standalone pymodbus register scanner with detailed descriptions
- `register_dump.txt` - Complete register dump output
- `upload_integration.sh` - Upload the integration to the Pi (restart required)
- `upload_dashboard.sh` - Upload dashboard to Pi (no restart needed)
- `upload_config.sh` - Upload config to Pi (restart required)
- `upload_package.sh` - Upload package to Pi (restart required)
- `hacs.json` - Lets HACS install the repo as a custom repository

## Integration Architecture (HA 2026.9 Modbus)
- `async_setup_entry` asks HA's `modbus` integration for a unit with `homeassistant.components.modbus.async_get_unit(hass, entry, ModbusTcpParams(host, port), unit_id)`; the config flow probes with `async_get_temporary_unit`. HA owns and shares the connection (one per endpoint, closed when the last holder unloads) — never open a connection yourself, never reload the entry on a dropped link.
- `modbus-connection` is **not** in our manifest `requirements`; it comes from `dependencies: ["modbus"]`, pinned by HA (4.10.0 in 2026.9.3). Pinning our own would fight HA's pin.
- Write against the 4.10.0 API, not the online docs: the docs track `dev`, which has `Device`, `UpdateReport`, `read_optional`, `unit.require_timeout()`. 4.10.0 has none of those, so `m_thermal_modbus/device.py` defines its own `UpdateReport` and poll loop. Check `homeassistant/components/modbus/manifest.json` at the target HA tag before using a newer API.
- Read plan: `Control` (0-22 range, reads 0-2) and `Readings` (`register_ranges=((100,199),)` → one 100-register read) every 30 s; `SetpointLimits` (201-204) with `max_span=1` because the 200+ block refuses multi-register reads. Limits are read once, retried after timeouts, and fall back to 5-25 / 25-55 if refused.
- Writes: power is `bit(0, 1)`, target is `bits(2, 0, 8)` — both read-modify-write, preserving the other bits/Zone 2 byte. `async_set_zone1_target` re-reads the mode and clamps; `async_set_mode` pulls an out-of-range setpoint into the new mode's range.
- Coordinator recycles the link (`unit.disconnect()`) after 3 consecutive timeouts — the EW11 can hold its socket open while RS-485 is dead.
- Run tests: `uv venv --python 3.14 && uv pip install -r requirements_test.txt && pytest`

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
| 118 | 40119 | ODU current | A (unscaled per the Midea PDF; `register_dump.txt`/`scan_registers.py` wrongly annotate it x0.1) |
| 119 | 40120 | ODU voltage | V |
| 124 | 40125 | Current error | Error code |
| 138 | 40139 | Water flow | m³/h (x0.01) |
| 143-144 | 40144-45 | Energy consumption | kWh (x0.01, 32-bit) |
| 148 | 40149 | Real-time heating capacity | kW (x0.01) |
| 150 | 40151 | Power consumption | kW (x0.01) |
| 151 | 40152 | COP | x0.01 |
| 199 | 40200 | Operation mode | 0=Off, 2=Cooling, 3=Heating, 5=DHW |

**Known issue**: Register 150 (Power consumption) reads 0 continuously while in Cooling mode on this unit, even with the compressor actively running (confirmed live: mode=2, compressor=41Hz, reg150=0). Works correctly in Heating mode. This is a firmware limitation on the heat pump, not an HA config issue — don't try to "fix" it by substituting another register; ODU current × voltage (`sensor.heat_pump_outdoor_unit_power`) is the only reliable live power figure while cooling, though it excludes the water pump.

### Entities (device name "Heat pump" → `<domain>.heat_pump_<key>`)
- **Controls**: `switch.heat_pump_power` (reg 0 bit 1), `select.heat_pump_mode` (reg 1: auto/cooling/heating), `number.heat_pump_target_temperature` (reg 2 low byte; min/max follow the live mode from regs 201-204)
- **Enum sensors**: `operating_state` (reg 101: idle/cooling/heating), `operation_mode` (reg 199: off/cooling/heating/dhw)
- **Derived in the library**: `cop` (reg 151, None when 0 or >10 — the raw register spikes), `outdoor_unit_power` (current × voltage, the only live power figure in cooling, see reg 150 issue), `water_temperature_delta` (T1 − Tw_in)
- **`energy_consumption`** (regs 143-144, uint32 ×0.01, raw 0 = no value): `RestoreSensor`, stays available while offline and ignores <1% dips, so LTS/Energy dashboard never see a false reset
- **Package**: `sensor.heat_pump_zone_1_activity` (template), `sensor.heat_pump_energy_daily/monthly/yearly` (utility meters on `energy_consumption`)

### Known Gotchas
- **`input_number.set_min_max` does not exist** as a service (only `set_value`, `increment`, `decrement`, `reload`), so an `input_number`'s range is static. That is why the target temperature is a native `number` entity whose `native_min_value`/`native_max_value` follow the mode.
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
- [x] Rebuild as a UI-configured integration on HA 2026.9 shared Modbus connections (`async_get_unit`), replacing the `modbus:` YAML hub, templates, `input_number` + automations and `set_target.py`
- [x] Improve EW11-A WiFi signal — moved "leni" AP to USB WiFi dongle with external antenna after M.2 HAT shielded built-in wlan0 antenna

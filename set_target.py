#!/usr/bin/env python3
"""Set Zone 1 target water temperature on Midea heat pump via Modbus TCP.

Called by Home Assistant automation (shell_command) when target temp changes.
Writes to register 2 which packs Zone1 (low byte) and Zone2 (high byte),
so we read first to preserve the Zone2 value.

Usage: python set_target.py <temperature>
Example: python set_target.py 35

Connection: EW11-A gateway at 10.10.100.131:8899, Modbus slave address 2.

Requires: pip install pymodbus
"""
import sys
from pymodbus.client import ModbusTcpClient

target = int(float(sys.argv[1]))
client = ModbusTcpClient('10.10.100.131', port=8899, timeout=5)
if client.connect():
    # Register 1 = mode (2=Cooling, 3=Heating); valid T1s range differs per mode
    mode_result = client.read_holding_registers(address=1, count=1, device_id=2)
    if not mode_result.isError():
        mode = mode_result.registers[0]
        low, high = (5, 25) if mode == 2 else (25, 55)
        target = max(low, min(target, high))

    # Register 2 packs two zones: low byte = Zone1, high byte = Zone2
    result = client.read_holding_registers(address=2, count=1, device_id=2)
    if not result.isError():
        zone2 = (result.registers[0] >> 8) & 0xFF
        new_raw = (zone2 << 8) | target
        client.write_register(address=2, value=new_raw, device_id=2)
    client.close()

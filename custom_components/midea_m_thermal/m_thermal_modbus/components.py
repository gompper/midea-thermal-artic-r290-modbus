"""Sub-systems of the Midea M-Thermal Modbus map, one Component each.

The wired controller serves three blocks. 0-22 (control) and 100-199
(operating parameters) answer bulk reads. 200-290 (configuration) refuses
them, so every register there is read on its own.
"""

from __future__ import annotations

from modbus_connection.model import Component, bit, bits, enum, gauge, integer, uint32

from .enums import ModeSetting, OperatingState, OperationMode

# Anything that answered a zone setpoint limit outside this is not a limit.
_MAX_SETPOINT = 99


class Control(Component):
    """Power, mode and water setpoint (holding registers 0-22)."""

    register_ranges = ((0, 22),)

    zone1_water_power = bit(0, 1, writable=True)
    """Zone 1 water temperature control. Register 0 is a bit field: bit 0 room
    control, bit 1 Zone 1 water, bit 2 DHW, bit 3 Zone 2 water."""

    mode = enum(1, ModeSetting, writable=True)
    """The mode the heat pump is told to run in."""

    zone1_target = bits(2, 0, 8, writable=True, unit="°C")
    """Zone 1 water setpoint T1s. Register 2 packs Zone 2 into its high byte,
    which a write leaves alone."""


class Readings(Component):
    """Operating parameters (holding registers 100-199), read as one block."""

    register_ranges = ((100, 199),)

    compressor_frequency = integer(100, signed=False, unit="Hz")
    operating_state = enum(101, OperatingState)

    water_inlet_temperature = integer(104, unit="°C")
    """Tw_in, the water entering the plate heat exchanger."""

    heat_exchanger_outlet_temperature = integer(105, unit="°C")
    """Tw_out, the water leaving the plate heat exchanger."""

    condenser_temperature = integer(106, unit="°C")
    """T3."""

    outdoor_temperature = integer(107, unit="°C")
    """T4, outdoor ambient."""

    discharge_temperature = integer(108, unit="°C")
    """Tp, compressor discharge."""

    suction_temperature = integer(109, unit="°C")
    """Th, compressor suction."""

    water_outlet_temperature = integer(110, unit="°C")
    """T1, total water outlet after any backup heater."""

    high_pressure = integer(116, signed=False, unit="kPa")
    low_pressure = integer(117, signed=False, unit="kPa")
    outdoor_unit_current = integer(118, signed=False, unit="A")
    outdoor_unit_voltage = integer(119, signed=False, unit="V")
    capacity = integer(123, signed=False, unit="kW")
    error_code = integer(124, signed=False)
    water_flow = gauge(138, 0.01, signed=False, unit="m³/h")

    energy_consumption = uint32(143, scale=0.01, nan=0, unit="kWh")
    """Lifetime electrical energy. The counter reads 0 while the unit has not
    reported it yet, which is no value rather than a reset."""

    heating_capacity = gauge(148, 0.01, signed=False, unit="kW")

    power_consumption = gauge(150, 0.01, signed=False, unit="kW")
    """Electrical power. Reads 0 in cooling mode on R290 firmware, even with
    the compressor running; `outdoor_unit_power` is the live figure then."""

    _cop = gauge(151, 0.01, signed=False)

    operation_mode = enum(199, OperationMode)

    @property
    def cop(self) -> float | None:
        """Heating COP, or None when idle or implausibly high.

        The register spikes to unrealistic values while the compressor ramps.
        """
        cop = self._cop
        if cop is None or not 0 < cop <= 10:
            return None
        return cop

    @property
    def outdoor_unit_power(self) -> float | None:
        """Outdoor unit power in W, from its current and voltage."""
        current = self.outdoor_unit_current
        voltage = self.outdoor_unit_voltage
        if current is None or voltage is None:
            return None
        return float(current * voltage)

    @property
    def water_temperature_delta(self) -> float | None:
        """T1 outlet minus Tw_in inlet."""
        outlet = self.water_outlet_temperature
        inlet = self.water_inlet_temperature
        if outlet is None or inlet is None:
            return None
        return float(outlet - inlet)


class SetpointLimits(Component):
    """Zone 1 water setpoint limits per mode (holding registers 201-204).

    Configuration registers answer one register per request.
    """

    max_span = 1

    cooling_max = bits(201, 0, 8, unit="°C")
    cooling_min = bits(202, 0, 8, unit="°C")
    heating_max = bits(203, 0, 8, unit="°C")
    heating_min = bits(204, 0, 8, unit="°C")

    def cooling_range(self) -> tuple[int, int] | None:
        """The cooling setpoint range, if the device reported a sane one."""
        return _sane_range(self.cooling_min, self.cooling_max)

    def heating_range(self) -> tuple[int, int] | None:
        """The heating setpoint range, if the device reported a sane one."""
        return _sane_range(self.heating_min, self.heating_max)


def _sane_range(low: int | None, high: int | None) -> tuple[int, int] | None:
    if low is None or high is None or not 0 <= low < high <= _MAX_SETPOINT:
        return None
    return low, high

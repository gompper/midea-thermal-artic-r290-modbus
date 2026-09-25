"""Register value enumerations of the Midea M-Thermal Modbus map."""

from enum import IntEnum


class ModeSetting(IntEnum):
    """The mode the heat pump is told to run in (register 1)."""

    AUTO = 1
    COOLING = 2
    HEATING = 3


class OperatingState(IntEnum):
    """What the heat pump is doing right now (register 101)."""

    IDLE = 0
    COOLING = 2
    HEATING = 3


class OperationMode(IntEnum):
    """The heat pump operation mode (register 199)."""

    OFF = 0
    COOLING = 2
    HEATING = 3
    DHW = 5

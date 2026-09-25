"""Tests for the device library, against the mock with no Home Assistant."""

from __future__ import annotations

from modbus_connection import (
    IllegalDataAddressError,
    ModbusConnectionError,
    ModbusTimeoutError,
)
from modbus_connection.mock import MockModbusUnit
import pytest

from custom_components.midea_m_thermal.m_thermal_modbus import (
    MideaHeatPump,
    ModeSetting,
    OperatingState,
    OperationMode,
)

from .conftest import ReusableMockConnection


@pytest.fixture
def device(mock_unit: MockModbusUnit) -> MideaHeatPump:
    """The heat pump on the mock unit."""
    return MideaHeatPump(mock_unit)


async def test_decodes_the_register_dump(device: MideaHeatPump) -> None:
    """Every field decodes the real dump to what the Midea table documents."""
    report = await device.async_update()

    assert report.updated == {"control", "readings"}
    assert not report.failed
    control, readings = device.control, device.readings
    assert control.zone1_water_power is True
    assert control.mode is ModeSetting.HEATING
    assert control.zone1_target == 28  # 7708 = 0x1E1C: Zone 2 30, Zone 1 28
    assert readings.compressor_frequency == 29
    assert readings.operating_state is OperatingState.HEATING
    assert readings.operation_mode is OperationMode.HEATING
    assert readings.water_inlet_temperature == 28
    assert readings.water_outlet_temperature == 32
    assert readings.outdoor_temperature == 4
    assert readings.outdoor_unit_current == 3
    assert readings.outdoor_unit_voltage == 223
    assert readings.outdoor_unit_power == 669
    assert readings.water_temperature_delta == 4
    assert readings.water_flow == pytest.approx(1.07)
    assert readings.energy_consumption == pytest.approx(317.18)
    assert readings.power_consumption == pytest.approx(0.87)
    assert readings.heating_capacity == pytest.approx(3.49)
    assert readings.cop == pytest.approx(4.01)
    assert readings.capacity == 10


async def test_reads_only_what_the_controller_serves(
    device: MideaHeatPump, mock_unit: MockModbusUnit
) -> None:
    """Two bulk reads per poll; the configuration block one register at a time."""
    await device.async_update()
    assert [(e.address, e.count) for e in mock_unit.read_events] == [
        (0, 3),
        (100, 100),
        (201, 1),
        (202, 1),
        (203, 1),
        (204, 1),
    ]

    mock_unit.read_events.clear()
    await device.async_update()
    # The limits are read once.
    assert [(e.address, e.count) for e in mock_unit.read_events] == [
        (0, 3),
        (100, 100),
    ]


async def test_decodes_negative_temperatures(
    device: MideaHeatPump, mock_unit: MockModbusUnit
) -> None:
    """Temperatures are 16-bit two's complement."""
    mock_unit.holding[107] = 65531
    await device.async_update()
    assert device.readings.outdoor_temperature == -5


@pytest.mark.parametrize(("raw", "expected"), [(0, None), (1100, None), (401, 4.01)])
async def test_cop_filters_idle_and_spikes(
    device: MideaHeatPump, mock_unit: MockModbusUnit, raw: int, expected: float | None
) -> None:
    """COP is None while idle and when it spikes past 10."""
    mock_unit.holding[151] = raw
    await device.async_update()
    assert device.readings.cop == expected


async def test_energy_counter_at_zero_is_no_value(
    device: MideaHeatPump, mock_unit: MockModbusUnit
) -> None:
    """A counter that reads 0 has not been reported yet; it is not a reset."""
    mock_unit.holding[143] = 1
    await device.async_update()
    assert device.readings.energy_consumption == pytest.approx(972.54)

    mock_unit.holding[143] = mock_unit.holding[144] = 0
    await device.async_update()
    assert device.readings.energy_consumption is None


async def test_setpoint_limits_come_from_the_device(
    device: MideaHeatPump, mock_unit: MockModbusUnit
) -> None:
    """The ranges follow registers 201-204, and Auto uses the heating range."""
    mock_unit.holding[201] = 0x1916  # cooling max 22
    mock_unit.holding[203] = 0x3732  # heating max 50
    await device.async_update()
    assert device.target_range(ModeSetting.COOLING) == (5, 22)
    assert device.target_range(ModeSetting.HEATING) == (25, 50)
    assert device.target_range(ModeSetting.AUTO) == (25, 50)
    assert device.target_range() == (25, 50)


async def test_refused_setpoint_limits_fall_back_to_defaults(
    device: MideaHeatPump, mock_unit: MockModbusUnit
) -> None:
    """A controller that refuses the limits keeps the documented ranges."""
    mock_unit.fail_read(201, IllegalDataAddressError())
    report = await device.async_update()
    assert report.updated == {"control", "readings"}
    assert device.target_range(ModeSetting.COOLING) == (5, 25)
    assert device.target_range(ModeSetting.HEATING) == (25, 55)

    # A refusal is final: the limits are not asked for again.
    mock_unit.read_events.clear()
    await device.async_update()
    assert all(e.address < 200 for e in mock_unit.read_events)


async def test_setpoint_limits_retry_after_a_timeout(
    device: MideaHeatPump, mock_unit: MockModbusUnit
) -> None:
    """A timeout reading the limits is retried on the next poll."""
    mock_unit.fail_read(203, ModbusTimeoutError("no answer"))
    await device.async_update()
    assert device.limits.heating_max is None

    mock_unit.fail_read(203, None)
    await device.async_update()
    assert device.limits.heating_max == 55


async def test_insane_setpoint_limits_fall_back_to_defaults(
    device: MideaHeatPump, mock_unit: MockModbusUnit
) -> None:
    """A range that is empty or holds the 0xFF sentinel is not trusted."""
    mock_unit.holding[203] = 0x19  # heating max 25, not above the minimum
    mock_unit.holding[202] = 0xFF
    await device.async_update()
    assert device.target_range(ModeSetting.HEATING) == (25, 55)
    assert device.target_range(ModeSetting.COOLING) == (5, 25)


async def test_set_target_keeps_zone_2(
    device: MideaHeatPump, mock_unit: MockModbusUnit
) -> None:
    """The Zone 1 setpoint shares its register with Zone 2, which is kept."""
    await device.async_update()
    assert await device.async_set_zone1_target(35) == 35
    assert mock_unit.holding[2] == 0x1E23


@pytest.mark.parametrize(
    ("mode", "requested", "written"),
    [
        (ModeSetting.HEATING, 70, 55),
        (ModeSetting.HEATING, 10, 25),
        (ModeSetting.COOLING, 35, 25),
        (ModeSetting.COOLING, 3, 5),
        (ModeSetting.AUTO, 20, 25),
    ],
)
async def test_set_target_clamps_to_the_live_mode(
    device: MideaHeatPump,
    mock_unit: MockModbusUnit,
    mode: ModeSetting,
    requested: int,
    written: int,
) -> None:
    """A setpoint outside the mode's range is clamped, with the mode read fresh."""
    await device.async_update()
    # Changed on the wired controller after the last poll.
    mock_unit.holding[1] = mode
    assert await device.async_set_zone1_target(requested) == written
    assert mock_unit.holding[2] & 0xFF == written


async def test_set_mode_pulls_the_setpoint_into_range(
    device: MideaHeatPump, mock_unit: MockModbusUnit
) -> None:
    """Switching to cooling with a heating setpoint moves the setpoint to 25."""
    await device.async_update()
    await device.async_set_zone1_target(40)

    await device.async_set_mode(ModeSetting.COOLING)

    assert mock_unit.holding[1] == ModeSetting.COOLING
    assert mock_unit.holding[2] == 0x1E19


async def test_set_mode_keeps_a_setpoint_in_range(
    device: MideaHeatPump, mock_unit: MockModbusUnit
) -> None:
    """A setpoint valid for the new mode is not written."""
    await device.async_update()
    writes = []
    mock_unit.on_write(writes.append)

    await device.async_set_mode(ModeSetting.AUTO)

    assert [event.address for event in writes] == [1]


async def test_set_power_touches_only_zone_1(
    device: MideaHeatPump, mock_unit: MockModbusUnit
) -> None:
    """Power flips bit 1 of register 0 and keeps the other zones' bits."""
    mock_unit.holding[0] = 0b1010  # Zone 2 water and Zone 1 water on
    await device.async_set_power(False)
    assert mock_unit.holding[0] == 0b1000
    await device.async_set_power(True)
    assert mock_unit.holding[0] == 0b1010


async def test_a_refused_component_does_not_fail_the_rest(
    device: MideaHeatPump, mock_unit: MockModbusUnit
) -> None:
    """A block the controller refuses lands in the report; the rest refresh."""
    mock_unit.fail_read(150, IllegalDataAddressError())
    report = await device.async_update()
    assert report.updated == {"control"}
    assert isinstance(report.failed["readings"], IllegalDataAddressError)


async def test_a_dropped_link_raises(
    device: MideaHeatPump, mock_unit: MockModbusUnit
) -> None:
    """A dead link is not a per-component failure."""
    mock_unit.fail_requests(ModbusConnectionError("gone"))
    with pytest.raises(ModbusConnectionError):
        await device.async_update()


async def test_a_timeout_before_any_answer_raises(
    device: MideaHeatPump, mock_unit: MockModbusUnit
) -> None:
    """Nothing answering at all is a timeout, not a report."""
    mock_unit.fail_requests(ModbusTimeoutError("silent"))
    with pytest.raises(ModbusTimeoutError):
        await device.async_update()


async def test_a_timeout_after_an_answer_is_reported(
    device: MideaHeatPump, mock_unit: MockModbusUnit
) -> None:
    """Once the controller has answered, a later timeout is per-component."""
    mock_unit.fail_read(100, ModbusTimeoutError("slow"))
    report = await device.async_update()
    assert report.updated == {"control"}
    assert isinstance(report.failed["readings"], ModbusTimeoutError)


async def test_raw_register_map(
    device: MideaHeatPump, mock_connection: ReusableMockConnection
) -> None:
    """Diagnostics get every register the device reads, undecoded."""
    raw = await device.async_read_raw()
    assert raw["holding"][2] == 7708
    assert raw["holding"][144] == 31718
    assert raw["holding"][203] == 14135

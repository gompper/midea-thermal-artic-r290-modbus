"""Tests for the Midea M-Thermal entities."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from modbus_connection import IllegalDataValueError, ModbusConnectionError
from modbus_connection.mock import MockModbusUnit
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from homeassistant.components.number import (
    ATTR_MAX,
    ATTR_MIN,
    ATTR_VALUE,
    SERVICE_SET_VALUE,
)
from homeassistant.components.select import ATTR_OPTION, SERVICE_SELECT_OPTION
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_UNIT_OF_MEASUREMENT,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

SCAN = timedelta(seconds=30)
TARGET = "number.heat_pump_target_temperature"
MODE = "select.heat_pump_mode"
POWER = "switch.heat_pump_power"
ENERGY = "sensor.heat_pump_energy_consumption"


async def _poll(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(SCAN)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


@pytest.mark.usefixtures("init_integration")
@pytest.mark.parametrize(
    ("entity_id", "state", "unit"),
    [
        ("sensor.heat_pump_operating_state", "heating", None),
        ("sensor.heat_pump_operation_mode", "heating", None),
        ("sensor.heat_pump_outdoor_temperature", "4", "°C"),
        ("sensor.heat_pump_water_inlet_temperature", "28", "°C"),
        ("sensor.heat_pump_water_outlet_temperature", "32", "°C"),
        ("sensor.heat_pump_heat_exchanger_outlet_temperature", "32", "°C"),
        ("sensor.heat_pump_discharge_temperature", "52", "°C"),
        ("sensor.heat_pump_suction_temperature", "3", "°C"),
        ("sensor.heat_pump_water_temperature_delta", "4.0", "°C"),
        ("sensor.heat_pump_water_flow", "1.07", "m³/h"),
        ("sensor.heat_pump_compressor_frequency", "29", "Hz"),
        ("sensor.heat_pump_high_pressure", "1350", "kPa"),
        ("sensor.heat_pump_low_pressure", "430", "kPa"),
        ("sensor.heat_pump_power_consumption", "0.87", "kW"),
        ("sensor.heat_pump_heating_capacity", "3.49", "kW"),
        ("sensor.heat_pump_cop", "4.01", None),
        ("sensor.heat_pump_outdoor_unit_current", "3", "A"),
        ("sensor.heat_pump_outdoor_unit_voltage", "223", "V"),
        ("sensor.heat_pump_outdoor_unit_power", "669.0", "W"),
        ("sensor.heat_pump_energy_consumption", "317.18", "kWh"),
        ("sensor.heat_pump_error_code", "0", None),
        (POWER, "on", None),
        (MODE, "heating", None),
        (TARGET, "28", "°C"),
    ],
)
async def test_entity_states(
    hass: HomeAssistant, entity_id: str, state: str, unit: str | None
) -> None:
    """Entities show the heat pump's register dump."""
    entity = hass.states.get(entity_id)
    assert entity is not None, entity_id
    assert entity.state == state
    assert entity.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == unit


@pytest.mark.usefixtures("init_integration")
async def test_target_range_follows_the_mode(
    hass: HomeAssistant, mock_unit: MockModbusUnit, freezer: FrozenDateTimeFactory
) -> None:
    """The setpoint bounds move with the mode, from the device's own limits."""
    state = hass.states.get(TARGET)
    assert (state.attributes[ATTR_MIN], state.attributes[ATTR_MAX]) == (25, 55)

    mock_unit.holding[1] = 2  # cooling, set on the wired controller
    mock_unit.holding[2] = 0x1E14  # 20 °C
    await _poll(hass, freezer)

    state = hass.states.get(TARGET)
    assert state.state == "20"
    assert (state.attributes[ATTR_MIN], state.attributes[ATTR_MAX]) == (5, 25)


@pytest.mark.usefixtures("init_integration")
async def test_set_target(hass: HomeAssistant, mock_unit: MockModbusUnit) -> None:
    """Setting the target writes Zone 1 and keeps Zone 2."""
    await hass.services.async_call(
        "number",
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: TARGET, ATTR_VALUE: 42},
        blocking=True,
    )
    assert mock_unit.holding[2] == 0x1E2A
    assert hass.states.get(TARGET).state == "42"


@pytest.mark.usefixtures("init_integration")
async def test_set_target_out_of_range_is_refused(
    hass: HomeAssistant, mock_unit: MockModbusUnit
) -> None:
    """Home Assistant refuses a setpoint the mode does not allow."""
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "number",
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: TARGET, ATTR_VALUE: 20},
            blocking=True,
        )
    assert mock_unit.holding[2] == 7708


@pytest.mark.usefixtures("init_integration")
async def test_select_cooling_moves_the_setpoint(
    hass: HomeAssistant, mock_unit: MockModbusUnit
) -> None:
    """Switching to cooling pulls a heating setpoint down to the cooling max."""
    await hass.services.async_call(
        "number",
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: TARGET, ATTR_VALUE: 40},
        blocking=True,
    )
    await hass.services.async_call(
        "select",
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: MODE, ATTR_OPTION: "cooling"},
        blocking=True,
    )
    assert mock_unit.holding[1] == 2
    assert mock_unit.holding[2] == 0x1E19

    await hass.async_block_till_done()
    assert hass.states.get(MODE).state == "cooling"
    state = hass.states.get(TARGET)
    assert state.state == "25"
    assert state.attributes[ATTR_MAX] == 25


@pytest.mark.usefixtures("init_integration")
async def test_power_switch(hass: HomeAssistant, mock_unit: MockModbusUnit) -> None:
    """The switch flips Zone 1 water control and nothing else."""
    mock_unit.holding[0] = 0b1010
    await hass.services.async_call(
        "switch", SERVICE_TURN_OFF, {ATTR_ENTITY_ID: POWER}, blocking=True
    )
    assert mock_unit.holding[0] == 0b1000
    assert hass.states.get(POWER).state == "off"

    await hass.services.async_call(
        "switch", SERVICE_TURN_ON, {ATTR_ENTITY_ID: POWER}, blocking=True
    )
    assert mock_unit.holding[0] == 0b1010
    assert hass.states.get(POWER).state == "on"


@pytest.mark.usefixtures("init_integration")
async def test_refused_write_raises(
    hass: HomeAssistant, mock_unit: MockModbusUnit
) -> None:
    """A write the heat pump rejects reaches the user as an error."""
    mock_unit.fail_write(1, IllegalDataValueError())
    with pytest.raises(HomeAssistantError, match="did not accept the change"):
        await hass.services.async_call(
            "select",
            SERVICE_SELECT_OPTION,
            {ATTR_ENTITY_ID: MODE, ATTR_OPTION: "auto"},
            blocking=True,
        )


@pytest.mark.usefixtures("init_integration")
async def test_cop_is_unknown_while_idle(
    hass: HomeAssistant, mock_unit: MockModbusUnit, freezer: FrozenDateTimeFactory
) -> None:
    """COP reads 0 while the compressor is off, which is no value."""
    mock_unit.holding[151] = 0
    await _poll(hass, freezer)
    assert hass.states.get("sensor.heat_pump_cop").state == STATE_UNKNOWN


@pytest.mark.usefixtures("init_integration")
async def test_energy_holds_through_outages_and_glitches(
    hass: HomeAssistant, mock_unit: MockModbusUnit, freezer: FrozenDateTimeFactory
) -> None:
    """The lifetime counter never gaps or dips, so statistics stay intact."""
    mock_unit.fail_requests(ModbusConnectionError("gone"))
    await _poll(hass, freezer)
    assert hass.states.get(ENERGY).state == "317.18"

    mock_unit.fail_requests(None)
    mock_unit.holding[144] = 0  # counter not reported
    await _poll(hass, freezer)
    assert hass.states.get(ENERGY).state == "317.18"

    mock_unit.holding[144] = 31700  # a rounding glitch just below the last value
    await _poll(hass, freezer)
    assert hass.states.get(ENERGY).state == "317.18"

    mock_unit.holding[144] = 31800
    await _poll(hass, freezer)
    assert hass.states.get(ENERGY).state == "318.0"


async def test_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    init_integration: MockConfigEntry,
) -> None:
    """Diagnostics carry the raw registers and redact the gateway address."""
    diagnostics = await get_diagnostics_for_config_entry(
        hass, hass_client, init_integration
    )
    assert diagnostics["entry"]["host"] == "**REDACTED**"
    assert diagnostics["updated"] == ["control", "readings"]
    assert diagnostics["failed"] == {}
    assert diagnostics["registers"]["holding"]["2"] == 7708
    assert diagnostics["registers"]["holding"]["144"] == 31718

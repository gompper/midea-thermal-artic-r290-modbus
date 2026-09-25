"""Tests for setting up and tearing down the Midea M-Thermal integration."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
from modbus_connection import (
    IllegalDataAddressError,
    ModbusConnectionError,
    ModbusTcpParams,
    ModbusTimeoutError,
)
from modbus_connection.mock import MockModbusUnit
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.midea_m_thermal.const import DOMAIN
from homeassistant.components.modbus import async_get_temporary_unit
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .conftest import ReusableMockConnection

SCAN = timedelta(seconds=30)


async def test_setup_and_unload(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_connection: ReusableMockConnection,
) -> None:
    """The entry loads over a shared unit, and unloading closes the link."""
    assert init_integration.state is ConfigEntryState.LOADED
    assert mock_connection.closes == 0

    await hass.config_entries.async_unload(init_integration.entry_id)

    assert init_integration.state is ConfigEntryState.NOT_LOADED
    assert mock_connection.closes == 1


async def test_device_info(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The heat pump is one device, named after the entry, with its capacity."""
    [device] = dr.async_entries_for_config_entry(
        dr.async_get(hass), init_integration.entry_id
    )
    assert device.identifiers == {(DOMAIN, init_integration.entry_id)}
    assert device.name == "Heat pump"
    assert device.manufacturer == "Midea"
    assert device.model == "M-Thermal 10 kW"


async def test_setup_retries_when_unreachable(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_unit: MockModbusUnit,
) -> None:
    """A heat pump that does not answer at startup is retried, not failed."""
    mock_unit.fail_requests(ModbusConnectionError("gateway down"))
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_goes_unavailable_and_recovers(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_unit: MockModbusUnit,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A dropped link marks entities unavailable until the next good poll.

    The entry is not reloaded; the link reopens on its own.
    """
    entity_id = "sensor.heat_pump_outdoor_temperature"
    assert hass.states.get(entity_id).state == "4"

    mock_unit.fail_requests(ModbusConnectionError("gone"))
    freezer.tick(SCAN)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

    mock_unit.fail_requests(None)
    freezer.tick(SCAN)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "4"
    assert init_integration.state is ConfigEntryState.LOADED


async def test_failed_component_marks_only_its_entities_unavailable(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_unit: MockModbusUnit,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Readings the controller refuses do not take the controls down."""
    mock_unit.fail_read(100, IllegalDataAddressError())
    freezer.tick(SCAN)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.heat_pump_outdoor_temperature").state == (
        STATE_UNAVAILABLE
    )
    assert hass.states.get("switch.heat_pump_power").state == "on"
    assert hass.states.get("number.heat_pump_target_temperature").state == "28"


async def test_wedged_link_is_recycled(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_unit: MockModbusUnit,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Three silent polls in a row drop the link so the next poll opens a new one."""
    mock_unit.fail_requests(ModbusTimeoutError("silent"))
    with patch.object(type(mock_unit), "disconnect", autospec=True) as disconnect:
        for _ in range(2):
            freezer.tick(SCAN)
            async_fire_time_changed(hass)
            await hass.async_block_till_done()
        disconnect.assert_not_called()

        freezer.tick(SCAN)
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        disconnect.assert_called_once()


async def test_connection_shared_with_another_integration(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_connection: ReusableMockConnection,
) -> None:
    """Another integration on the same gateway rides the same link.

    The link outlives whichever holder leaves first and closes behind the last.
    """
    params = ModbusTcpParams(host="10.10.100.131", port=8899)
    with patch(
        "homeassistant.components.modbus.connection.ModbusConnection"
    ) as second_link:
        async with async_get_temporary_unit(hass, params, 5):
            second_link.assert_not_called()
            await hass.config_entries.async_unload(init_integration.entry_id)
            assert mock_connection.closes == 0
    assert mock_connection.closes == 1

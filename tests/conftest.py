"""Fixtures for the Midea M-Thermal tests.

The heat pump is modbus-connection's in-memory mock, loaded with the register
dump of a real Thermal Arctic R290 10 kW. Home Assistant's shared-connection
code runs for real; only the backend under it is swapped.
"""

from __future__ import annotations

from collections.abc import Generator
import json
from pathlib import Path
from unittest.mock import patch

from modbus_connection.mock import MockModbusConnection, MockModbusUnit
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.midea_m_thermal.const import CONF_UNIT_ID, DOMAIN
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant

UNIT_ID = 2
ENTRY_DATA = {CONF_HOST: "10.10.100.131", CONF_PORT: 8899, CONF_UNIT_ID: UNIT_ID}

SNAPSHOT = json.loads(
    (Path(__file__).parent / "fixtures" / "registers.json").read_text()
)


class ReusableMockConnection(MockModbusConnection):
    """A mock heat pump that outlives close(), so a reloaded entry finds it again.

    A real connection is closed for good; Home Assistant builds a new one on the
    next setup. Here every setup gets this same object, so close() only drops
    the link and counts.
    """

    closes = 0

    async def close(self) -> None:
        """Record the close and drop the link."""
        self.closes += 1
        await self.disconnect()


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load the integration under test."""


@pytest.fixture
def mock_connection() -> Generator[ReusableMockConnection]:
    """Back every shared Modbus connection with one in-memory heat pump."""
    connection = ReusableMockConnection()
    connection.for_unit(UNIT_ID).load_raw(
        {
            space: {int(address): value for address, value in values.items()}
            for space, values in SNAPSHOT.items()
        }
    )
    with patch(
        "homeassistant.components.modbus.connection.ModbusConnection",
        return_value=connection,
    ):
        yield connection


@pytest.fixture
def mock_unit(mock_connection: ReusableMockConnection) -> MockModbusUnit:
    """The heat pump on the mock connection."""
    return mock_connection.for_unit(UNIT_ID)


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """A config entry for the heat pump."""
    return MockConfigEntry(domain=DOMAIN, title="Heat pump", data=ENTRY_DATA)


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_connection: ReusableMockConnection,
) -> MockConfigEntry:
    """Set up the integration against the mock heat pump."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry

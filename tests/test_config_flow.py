"""Tests for the Midea M-Thermal config flow."""

from __future__ import annotations

from modbus_connection import ModbusConnectionError
from modbus_connection.mock import MockModbusUnit
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.midea_m_thermal.const import CONF_UNIT_ID, DOMAIN
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import ENTRY_DATA, ReusableMockConnection


async def test_user_flow(
    hass: HomeAssistant, mock_connection: ReusableMockConnection
) -> None:
    """The flow probes the heat pump and creates the entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], ENTRY_DATA
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Heat pump"
    assert result["data"] == ENTRY_DATA
    # The probe's temporary hold was the only one, so the link was closed.
    assert mock_connection.closes == 1


@pytest.mark.parametrize(
    ("setup", "error"),
    [
        (
            lambda unit: unit.fail_requests(ModbusConnectionError("refused")),
            "cannot_connect",
        ),
        (lambda unit: unit.holding.__setitem__(1, 0), "not_a_heat_pump"),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant, mock_unit: MockModbusUnit, setup, error: str
) -> None:
    """A heat pump that cannot be used shows an error, and the flow recovers."""
    original_mode = mock_unit.holding[1]
    setup(mock_unit)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], ENTRY_DATA
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    mock_unit.fail_requests(None)
    mock_unit.holding[1] = original_mode
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], ENTRY_DATA
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_wrong_unit_id(
    hass: HomeAssistant, mock_connection: ReusableMockConnection
) -> None:
    """A unit id nothing answers on cannot connect."""
    mock_connection.for_unit(1).fail_requests(ModbusConnectionError("no route"))
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**ENTRY_DATA, CONF_UNIT_ID: 1}
    )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_already_configured(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_connection: ReusableMockConnection,
) -> None:
    """The same gateway and unit id cannot be added twice."""
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], ENTRY_DATA
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_connection: ReusableMockConnection,
) -> None:
    """The gateway address can change without re-adding the heat pump."""
    mock_connection.for_unit(3).load_raw({"holding": {0: 2, 1: 3, 2: 30}})
    result = await init_integration.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM

    new_data = {CONF_HOST: "10.10.100.132", CONF_PORT: 502, CONF_UNIT_ID: 3}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], new_data)

    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert dict(init_integration.data) == new_data


async def test_reconfigure_cannot_connect(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_unit: MockModbusUnit,
) -> None:
    """An unreachable heat pump keeps the old settings."""
    result = await init_integration.start_reconfigure_flow(hass)
    mock_unit.fail_requests(ModbusConnectionError("gone"))
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], ENTRY_DATA
    )
    assert result["errors"] == {"base": "cannot_connect"}
    assert dict(init_integration.data) == ENTRY_DATA

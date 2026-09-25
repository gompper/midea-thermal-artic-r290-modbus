"""Diagnostics for Midea M-Thermal heat pumps."""

from __future__ import annotations

from typing import Any

from modbus_connection import ModbusError

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .coordinator import MideaConfigEntry

TO_REDACT = {CONF_HOST}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MideaConfigEntry
) -> dict[str, Any]:
    """Return the raw register map, read fresh, with the poll status.

    The register map replays into modbus-connection's mock backend with
    ``load_raw()``, so a download can back a regression test.
    """
    coordinator = entry.runtime_data
    try:
        registers: dict[str, Any] = await coordinator.device.async_read_raw()
    except ModbusError as err:
        registers = {"error": str(err)}
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "updated": sorted(coordinator.data.updated),
        "failed": {name: str(err) for name, err in coordinator.data.failed.items()},
        "registers": registers,
    }

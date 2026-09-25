"""Config flow for Midea M-Thermal heat pumps."""

from __future__ import annotations

import logging
from typing import Any

from modbus_connection import ModbusError, ModbusTcpParams
import voluptuous as vol

from homeassistant.components.modbus import async_get_temporary_unit
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
)

from .const import CONF_UNIT_ID, DEFAULT_NAME, DEFAULT_PORT, DEFAULT_UNIT_ID, DOMAIN
from .m_thermal_modbus import MideaHeatPump

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): TextSelector(),
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
            NumberSelector(
                NumberSelectorConfig(min=1, max=65535, mode=NumberSelectorMode.BOX)
            ),
            vol.Coerce(int),
        ),
        vol.Required(CONF_UNIT_ID, default=DEFAULT_UNIT_ID): vol.All(
            NumberSelector(
                NumberSelectorConfig(min=1, max=247, mode=NumberSelectorMode.BOX)
            ),
            vol.Coerce(int),
        ),
    }
)


class NotAHeatPump(Exception):
    """The unit answered, but not like a Midea M-Thermal heat pump."""


async def _async_probe(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Read the control registers, or raise if the heat pump does not answer."""
    params = ModbusTcpParams(host=data[CONF_HOST], port=data[CONF_PORT])
    async with async_get_temporary_unit(hass, params, data[CONF_UNIT_ID]) as unit:
        device = MideaHeatPump(unit)
        await device.control.async_update()
    if device.control.mode is None:
        raise NotAHeatPump


class MideaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Midea M-Thermal."""

    VERSION = 1

    async def _async_validate(
        self, user_input: dict[str, Any], errors: dict[str, str]
    ) -> bool:
        """Probe the heat pump, filling in errors if it cannot be used."""
        try:
            await _async_probe(self.hass, user_input)
        except (ModbusError, HomeAssistantError) as err:
            _LOGGER.debug("Cannot reach the heat pump: %s", err)
            errors["base"] = "cannot_connect"
        except NotAHeatPump:
            errors["base"] = "not_a_heat_pump"
        except Exception:
            _LOGGER.exception("Unexpected error probing the heat pump")
            errors["base"] = "unknown"
        return not errors

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the gateway and unit id."""
        errors: dict[str, str] = {}
        if user_input is not None:
            # The heat pump reports no serial number, so its address is its identity.
            self._async_abort_entries_match(user_input)
            if await self._async_validate(user_input, errors):
                return self.async_create_entry(title=DEFAULT_NAME, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, user_input
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the gateway or unit id of an existing entry."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input != dict(entry.data):
                self._async_abort_entries_match(user_input)
            if await self._async_validate(user_input, errors):
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, user_input or entry.data
            ),
            errors=errors,
        )

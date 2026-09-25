"""Data update coordinator for Midea M-Thermal heat pumps."""

from __future__ import annotations

import logging

from modbus_connection import ModbusError, ModbusTimeoutError
from propcache.api import cached_property

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, MANUFACTURER, SCAN_INTERVAL
from .m_thermal_modbus import MideaHeatPump, UpdateReport

_LOGGER = logging.getLogger(__name__)

# Timeouts in a row after which the link counts as wedged rather than slow. The
# EW11 can keep its socket open while the RS-485 side stops answering.
_WEDGED_AFTER_TIMEOUTS = 3

type MideaConfigEntry = ConfigEntry[MideaDataUpdateCoordinator]


class MideaDataUpdateCoordinator(DataUpdateCoordinator[UpdateReport]):
    """Poll the heat pump's control and operating registers."""

    config_entry: MideaConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: MideaConfigEntry, device: MideaHeatPump
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=entry.title,
            update_interval=SCAN_INTERVAL,
        )
        self.device = device
        self._timeouts = 0
        self._failed: frozenset[str] = frozenset()

    async def _async_update_data(self) -> UpdateReport:
        try:
            report = await self.device.async_update()
        except ModbusTimeoutError as err:
            self._timeouts += 1
            if self._timeouts >= _WEDGED_AFTER_TIMEOUTS:
                self._timeouts = 0
                await self.device.unit.disconnect()
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="communication_error",
                translation_placeholders={"error": str(err)},
            ) from err
        except ModbusError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="communication_error",
                translation_placeholders={"error": str(err)},
            ) from err
        self._timeouts = 0

        if not report.updated:
            errors = list(report.failed.values())
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="communication_error",
                translation_placeholders={"error": str(errors[0])},
            ) from ExceptionGroup("every sub-system failed", errors)

        for name in sorted(report.failed.keys() - self._failed):
            _LOGGER.warning("Failed to read %s: %s", name, report.failed[name])
        self._failed = frozenset(report.failed)
        return report

    @cached_property
    def device_info(self) -> DeviceInfo:
        """Describe the heat pump to the device registry."""
        capacity = self.device.readings.capacity
        return DeviceInfo(
            identifiers={(DOMAIN, self.config_entry.entry_id)},
            manufacturer=MANUFACTURER,
            model=f"M-Thermal {capacity} kW" if capacity else "M-Thermal",
            name=self.config_entry.title,
        )

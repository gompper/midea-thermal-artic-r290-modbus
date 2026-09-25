"""The Midea M-Thermal heat pump, reached through a ModbusUnit."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import logging
from typing import TYPE_CHECKING, Any

from modbus_connection import (
    ModbusConnectionError,
    ModbusError,
    ModbusExceptionError,
    ModbusTimeoutError,
)

from .components import Control, Readings, SetpointLimits
from .enums import ModeSetting

if TYPE_CHECKING:
    from modbus_connection import ModbusUnit

_LOGGER = logging.getLogger(__name__)

# Sub-systems read on every poll, by attribute name.
POLLED = ("control", "readings")

# Zone 1 setpoint ranges from the Midea documentation, used until the device
# reports its own.
DEFAULT_COOLING_RANGE = (5, 25)
DEFAULT_HEATING_RANGE = (25, 55)

type Raw = dict[str, dict[int, Any]]


@dataclass(frozen=True)
class UpdateReport:
    """Which sub-systems a poll refreshed, and why the others failed."""

    updated: frozenset[str]
    failed: Mapping[str, ModbusError] = field(default_factory=dict)


class MideaHeatPump:
    """A Midea M-Thermal heat pump on a Modbus unit.

    The unit is shared and owned by the caller; this object only reads and
    writes registers through it.
    """

    def __init__(self, unit: ModbusUnit) -> None:
        """Model the heat pump behind a unit."""
        self.unit = unit
        self.control = Control(unit)
        self.readings = Readings(unit)
        self.limits = SetpointLimits(unit)
        self._limits_pending = True

    async def async_update(self) -> UpdateReport:
        """Refresh every polled sub-system, each on its own.

        A sub-system the device rejects lands in the report and the rest still
        refresh. A dropped link raises at once, and so does a timeout before
        anything answered, since that means nothing is listening.
        """
        updated: set[str] = set()
        failed: dict[str, ModbusError] = {}
        for name in POLLED:
            try:
                await getattr(self, name).async_update()
            except ModbusConnectionError:
                raise
            except ModbusTimeoutError as err:
                if not updated:
                    raise
                failed[name] = err
            except ModbusError as err:
                failed[name] = err
            else:
                updated.add(name)
        if self._limits_pending and updated:
            await self._async_read_limits()
        return UpdateReport(frozenset(updated), failed)

    async def _async_read_limits(self) -> None:
        """Read the setpoint limits once; they only change in the installer menu.

        Until they are read, and for good if the device refuses them, the
        documented defaults apply.
        """
        try:
            await self.limits.async_update()
        except ModbusExceptionError as err:
            _LOGGER.warning(
                "The heat pump refused its setpoint limits, using the defaults: %s",
                err,
            )
        except ModbusError as err:
            _LOGGER.debug("Could not read the setpoint limits, will retry: %s", err)
            return
        self._limits_pending = False

    def target_range(self, mode: ModeSetting | None = None) -> tuple[int, int]:
        """The Zone 1 setpoint range for a mode, the current mode by default.

        Auto follows the heating range.
        """
        if mode is None:
            mode = self.control.mode
        if mode is ModeSetting.COOLING:
            return self.limits.cooling_range() or DEFAULT_COOLING_RANGE
        return self.limits.heating_range() or DEFAULT_HEATING_RANGE

    async def async_set_power(self, on: bool) -> None:
        """Switch Zone 1 water temperature control, keeping the other bits."""
        await self.control.write("zone1_water_power", on)

    async def async_set_zone1_target(self, value: int) -> int:
        """Write the Zone 1 setpoint, clamped into the live mode's range.

        The mode is read fresh, so a mode changed on the wired controller since
        the last poll is honoured. Returns the value written.
        """
        await self.control.async_update(notify=False)
        low, high = self.target_range()
        target = max(low, min(int(value), high))
        await self.control.write("zone1_target", target)
        return target

    async def async_set_mode(self, mode: ModeSetting) -> None:
        """Switch mode, then pull the setpoint into the new mode's range.

        Both modes share one setpoint register, so a heating setpoint of 35 °C
        is out of range once the heat pump is cooling.
        """
        await self.control.write("mode", mode)
        await self.control.async_update(notify=False)
        target = self.control.zone1_target
        low, high = self.target_range(mode)
        if target is not None and not low <= target <= high:
            await self.control.write("zone1_target", max(low, min(target, high)))

    async def async_read_raw(self) -> Raw:
        """Every register this device reads, undecoded, for diagnostics."""
        merged: Raw = {}
        for component in (self.control, self.readings, self.limits):
            for space, values in (await component.async_read_raw()).items():
                merged.setdefault(space, {}).update(values)
        return merged

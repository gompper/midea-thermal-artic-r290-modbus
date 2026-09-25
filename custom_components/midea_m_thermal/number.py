"""Water setpoint of a Midea M-Thermal heat pump."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MideaConfigEntry
from .entity import MideaEntity, MideaEntityDescription

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class MideaNumberEntityDescription(NumberEntityDescription, MideaEntityDescription):
    """Describe a heat pump number."""


TARGET_TEMPERATURE = MideaNumberEntityDescription(
    key="target_temperature",
    translation_key="target_temperature",
    component="control",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MideaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the heat pump setpoint."""
    async_add_entities([MideaTargetTemperature(entry.runtime_data, TARGET_TEMPERATURE)])


class MideaTargetTemperature(MideaEntity, NumberEntity):
    """The Zone 1 water setpoint, bounded by the active mode's range.

    Cooling and heating share the setpoint register and differ only in its
    valid range, so the bounds move with the mode.
    """

    entity_description: MideaNumberEntityDescription

    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    @property
    def native_value(self) -> int | None:
        """Return the setpoint."""
        return self.coordinator.device.control.zone1_target

    @property
    def native_min_value(self) -> float:
        """Return the lowest setpoint the current mode accepts."""
        return self.coordinator.device.target_range()[0]

    @property
    def native_max_value(self) -> float:
        """Return the highest setpoint the current mode accepts."""
        return self.coordinator.device.target_range()[1]

    async def async_set_native_value(self, value: float) -> None:
        """Write the setpoint."""
        await self._async_write(
            self.coordinator.device.async_set_zone1_target(round(value))
        )

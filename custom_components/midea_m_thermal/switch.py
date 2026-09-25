"""Power switch of a Midea M-Thermal heat pump."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MideaConfigEntry
from .entity import MideaEntity, MideaEntityDescription

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class MideaSwitchEntityDescription(SwitchEntityDescription, MideaEntityDescription):
    """Describe a heat pump switch."""


POWER = MideaSwitchEntityDescription(
    key="power", translation_key="power", component="control"
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MideaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the heat pump power switch."""
    async_add_entities([MideaPowerSwitch(entry.runtime_data, POWER)])


class MideaPowerSwitch(MideaEntity, SwitchEntity):
    """Zone 1 water temperature control, the heat pump's power on this setup.

    Only its bit of the power register is touched, so room, DHW and Zone 2
    control keep whatever state they have.
    """

    entity_description: MideaSwitchEntityDescription

    @property
    def is_on(self) -> bool | None:
        """Return whether Zone 1 water temperature control is on."""
        return self.coordinator.device.control.zone1_water_power

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn Zone 1 water temperature control on."""
        await self._async_write(self.coordinator.device.async_set_power(True))

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn Zone 1 water temperature control off."""
        await self._async_write(self.coordinator.device.async_set_power(False))

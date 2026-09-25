"""Mode selection of a Midea M-Thermal heat pump."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MideaConfigEntry
from .entity import MideaEntity, MideaEntityDescription
from .m_thermal_modbus import ModeSetting

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class MideaSelectEntityDescription(SelectEntityDescription, MideaEntityDescription):
    """Describe a heat pump select."""


MODE = MideaSelectEntityDescription(
    key="mode",
    translation_key="mode",
    component="control",
    options=[mode.name.lower() for mode in ModeSetting],
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MideaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the heat pump mode select."""
    async_add_entities([MideaModeSelect(entry.runtime_data, MODE)])


class MideaModeSelect(MideaEntity, SelectEntity):
    """Auto, cooling or heating."""

    entity_description: MideaSelectEntityDescription

    @property
    def current_option(self) -> str | None:
        """Return the mode the heat pump is told to run in."""
        mode = self.coordinator.device.control.mode
        return mode.name.lower() if mode is not None else None

    async def async_select_option(self, option: str) -> None:
        """Switch mode, moving the setpoint into the new mode's range."""
        await self._async_write(
            self.coordinator.device.async_set_mode(ModeSetting[option.upper()])
        )

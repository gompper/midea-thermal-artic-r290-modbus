"""Base entity for Midea M-Thermal heat pumps."""

from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass

from modbus_connection import ModbusError

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MideaDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class MideaEntityDescription(EntityDescription):
    """Describe an entity backed by one of the heat pump's sub-systems."""

    component: str
    """Attribute name of the sub-system on MideaHeatPump that it reads."""


class MideaEntity(CoordinatorEntity[MideaDataUpdateCoordinator]):
    """An entity of the heat pump device."""

    _attr_has_entity_name = True
    entity_description: MideaEntityDescription

    def __init__(
        self,
        coordinator: MideaDataUpdateCoordinator,
        description: MideaEntityDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"
        self._attr_device_info = coordinator.device_info

    @property
    def available(self) -> bool:
        """Whether this entity's sub-system answered the last poll."""
        return (
            super().available
            and self.entity_description.component not in self.coordinator.data.failed
        )

    async def _async_write(self, write: Awaitable[object]) -> None:
        """Run a write against the heat pump, then poll for the result.

        The poll is not debounced, so a second change in quick succession still
        shows the heat pump's state rather than the one before it.
        """
        try:
            await write
        except ModbusError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        await self.coordinator.async_refresh()

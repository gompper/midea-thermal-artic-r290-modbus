"""Sensors of a Midea M-Thermal heat pump."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MideaConfigEntry
from .entity import MideaEntity, MideaEntityDescription
from .m_thermal_modbus import MideaHeatPump, OperatingState, OperationMode

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class MideaSensorEntityDescription(SensorEntityDescription, MideaEntityDescription):
    """Describe a heat pump sensor."""

    component: str = "readings"
    value_fn: Callable[[MideaHeatPump], float | int | str | None]


def _temperature(
    key: str, value_fn: Callable[[MideaHeatPump], float | int | None]
) -> MideaSensorEntityDescription:
    return MideaSensorEntityDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=value_fn,
    )


def _enum_name(value: OperatingState | OperationMode | None) -> str | None:
    return value.name.lower() if value is not None else None


SENSORS: tuple[MideaSensorEntityDescription, ...] = (
    MideaSensorEntityDescription(
        key="operating_state",
        translation_key="operating_state",
        device_class=SensorDeviceClass.ENUM,
        options=[state.name.lower() for state in OperatingState],
        value_fn=lambda device: _enum_name(device.readings.operating_state),
    ),
    MideaSensorEntityDescription(
        key="operation_mode",
        translation_key="operation_mode",
        device_class=SensorDeviceClass.ENUM,
        options=[mode.name.lower() for mode in OperationMode],
        value_fn=lambda device: _enum_name(device.readings.operation_mode),
    ),
    _temperature(
        "outdoor_temperature", lambda device: device.readings.outdoor_temperature
    ),
    _temperature(
        "water_inlet_temperature",
        lambda device: device.readings.water_inlet_temperature,
    ),
    _temperature(
        "water_outlet_temperature",
        lambda device: device.readings.water_outlet_temperature,
    ),
    _temperature(
        "heat_exchanger_outlet_temperature",
        lambda device: device.readings.heat_exchanger_outlet_temperature,
    ),
    _temperature(
        "condenser_temperature", lambda device: device.readings.condenser_temperature
    ),
    _temperature(
        "discharge_temperature", lambda device: device.readings.discharge_temperature
    ),
    _temperature(
        "suction_temperature", lambda device: device.readings.suction_temperature
    ),
    MideaSensorEntityDescription(
        key="water_temperature_delta",
        translation_key="water_temperature_delta",
        device_class=SensorDeviceClass.TEMPERATURE_DELTA,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.readings.water_temperature_delta,
    ),
    MideaSensorEntityDescription(
        key="water_flow",
        translation_key="water_flow",
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda device: device.readings.water_flow,
    ),
    MideaSensorEntityDescription(
        key="compressor_frequency",
        translation_key="compressor_frequency",
        device_class=SensorDeviceClass.FREQUENCY,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.readings.compressor_frequency,
    ),
    MideaSensorEntityDescription(
        key="high_pressure",
        translation_key="high_pressure",
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.KPA,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.readings.high_pressure,
    ),
    MideaSensorEntityDescription(
        key="low_pressure",
        translation_key="low_pressure",
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.KPA,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.readings.low_pressure,
    ),
    MideaSensorEntityDescription(
        key="power_consumption",
        translation_key="power_consumption",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda device: device.readings.power_consumption,
    ),
    MideaSensorEntityDescription(
        key="heating_capacity",
        translation_key="heating_capacity",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda device: device.readings.heating_capacity,
    ),
    MideaSensorEntityDescription(
        key="cop",
        translation_key="cop",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda device: device.readings.cop,
    ),
    MideaSensorEntityDescription(
        key="outdoor_unit_current",
        translation_key="outdoor_unit_current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.readings.outdoor_unit_current,
    ),
    MideaSensorEntityDescription(
        key="outdoor_unit_voltage",
        translation_key="outdoor_unit_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.readings.outdoor_unit_voltage,
    ),
    MideaSensorEntityDescription(
        key="outdoor_unit_power",
        translation_key="outdoor_unit_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda device: device.readings.outdoor_unit_power,
    ),
    MideaSensorEntityDescription(
        key="energy_consumption",
        translation_key="energy_consumption",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=lambda device: device.readings.energy_consumption,
    ),
    MideaSensorEntityDescription(
        key="error_code",
        translation_key="error_code",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: device.readings.error_code,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MideaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the heat pump sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        (
            MideaTotalSensor
            if description.state_class is SensorStateClass.TOTAL_INCREASING
            else MideaSensor
        )(coordinator, description)
        for description in SENSORS
    )


class MideaSensor(MideaEntity, SensorEntity):
    """A heat pump reading."""

    entity_description: MideaSensorEntityDescription

    @property
    def native_value(self) -> float | int | str | None:
        """Return the value the heat pump reported."""
        return self.entity_description.value_fn(self.coordinator.device)


class MideaTotalSensor(MideaEntity, RestoreSensor):
    """A lifetime counter that keeps its last value while the heat pump is away.

    A gap or a spurious drop would damage long-term statistics and the energy
    dashboard, so the value is restored across restarts and never shrinks by a
    rounding glitch.
    """

    entity_description: MideaSensorEntityDescription

    @property
    def available(self) -> bool:
        """Stay available so statistics hold their last value."""
        return True

    async def async_added_to_hass(self) -> None:
        """Restore the last value, then take the current one."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_sensor_data()) is not None:
            self._attr_native_value = last.native_value
        self._process_value()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._process_value()
        super()._handle_coordinator_update()

    def _process_value(self) -> None:
        value = self.entity_description.value_fn(self.coordinator.device)
        if not isinstance(value, (int, float)):
            return
        last = self._attr_native_value
        if isinstance(last, (int, float)) and last * 0.99 <= value < last:
            return  # a firmware glitch reading slightly low, not a meter reset
        self._attr_native_value = value

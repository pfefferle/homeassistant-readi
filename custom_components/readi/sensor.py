"""Sensors for the re@di Open Data integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    DEGREE,
    PERCENTAGE,
    UnitOfIrradiance,
    UnitOfLength,
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfVolumetricFlux,
    EntityCategory,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util, slugify

from .const import (
    DOMAIN,
    KIND_TEMPERATURE,
    KIND_TRAFFIC,
    KIND_WEATHER,
    PORTAL_URL,
    TEMPERATURE_PACKAGE,
    TRAFFIC_PACKAGE,
    WEATHER_PACKAGE,
)
from .coordinator import ReadiConfigEntry, ReadiCoordinator, device_id
from .parse import is_fresh

PARALLEL_UPDATES = 0

MAX_AGE = {
    KIND_TEMPERATURE: timedelta(hours=2),
    KIND_WEATHER: timedelta(hours=2),
    KIND_TRAFFIC: timedelta(hours=3),
}
# The entity that carries the sensor's position for the map.
MAP_ENTITY = {
    KIND_TEMPERATURE: "temperature",
    KIND_WEATHER: "temp_avg",
    KIND_TRAFFIC: "total",
}
PACKAGES = {
    KIND_TEMPERATURE: TEMPERATURE_PACKAGE,
    KIND_WEATHER: WEATHER_PACKAGE,
    KIND_TRAFFIC: TRAFFIC_PACKAGE,
}


@dataclass(frozen=True, kw_only=True)
class ReadiSensorDescription(SensorEntityDescription):
    """A value of a portal sensor; key is the value name."""


def _temp(key: str, translation_key: str, enabled: bool = True) -> ReadiSensorDescription:
    return ReadiSensorDescription(
        key=key,
        translation_key=translation_key,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=enabled,
    )


TEMPERATURE_SENSORS = (
    _temp("temperature", "temperature"),
    ReadiSensorDescription(
        key="humidity",
        translation_key="humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)

WEATHER_SENSORS = (
    _temp("temp_avg", "temperature"),
    ReadiSensorDescription(
        key="rel_hum_avg",
        translation_key="humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ReadiSensorDescription(
        key="rel_press_avg",
        translation_key="pressure",
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        native_unit_of_measurement=UnitOfPressure.HPA,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ReadiSensorDescription(
        key="precip_abs",
        translation_key="precipitation_total",
        device_class=SensorDeviceClass.PRECIPITATION,
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    ReadiSensorDescription(
        key="precip_abs_int",
        translation_key="precipitation_intensity",
        device_class=SensorDeviceClass.PRECIPITATION_INTENSITY,
        native_unit_of_measurement=UnitOfVolumetricFlux.MILLIMETERS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ReadiSensorDescription(
        key="wnd_spd_avg",
        translation_key="wind_speed",
        device_class=SensorDeviceClass.WIND_SPEED,
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ReadiSensorDescription(
        key="wnd_spd_max",
        translation_key="wind_gust",
        device_class=SensorDeviceClass.WIND_SPEED,
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ReadiSensorDescription(
        key="wnd_dir_compass_corr",
        translation_key="wind_direction",
        device_class=SensorDeviceClass.WIND_DIRECTION,
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT_ANGLE,
    ),
    ReadiSensorDescription(
        key="global_rad",
        translation_key="global_radiation",
        device_class=SensorDeviceClass.IRRADIANCE,
        native_unit_of_measurement=UnitOfIrradiance.WATTS_PER_SQUARE_METER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    _temp("dew_pt_avg", "dew_point", enabled=False),
    _temp("wet_bulb_temp", "wet_bulb_temperature", enabled=False),
    _temp("windchill_temp", "wind_chill", enabled=False),
    ReadiSensorDescription(
        key="air_density",
        translation_key="air_density",
        native_unit_of_measurement="kg/m³",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    ReadiSensorDescription(
        key="spec_enthalpy",
        translation_key="specific_enthalpy",
        native_unit_of_measurement="kJ/kg",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    ReadiSensorDescription(
        key="abs_hum_avg",
        translation_key="absolute_humidity",
        device_class=SensorDeviceClass.ABSOLUTE_HUMIDITY,
        native_unit_of_measurement="g/m³",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    ReadiSensorDescription(
        key="abs_press_avg",
        translation_key="pressure_absolute",
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        native_unit_of_measurement=UnitOfPressure.HPA,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    ReadiSensorDescription(
        key="flash_interval",
        translation_key="lightning_interval",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    ReadiSensorDescription(
        key="flash_minute",
        translation_key="lightning_minute",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
)

TRAFFIC_CLASS_KEYS = {
    "PKW": "vehicles_car",
    "LKW": "vehicles_truck",
    "LKW+Anhänger": "vehicles_truck_trailer",
    "Leichtes Nutzfahrzeug": "vehicles_van",
    "Motorrad": "vehicles_motorcycle",
}

TRAFFIC_SENSORS = (
    ReadiSensorDescription(
        key="total",
        translation_key="vehicles",
        native_unit_of_measurement="vehicles/h",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ReadiSensorDescription(
        key="avg_speed",
        translation_key="average_speed",
        device_class=SensorDeviceClass.SPEED,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    *(
        ReadiSensorDescription(
            key=f"class:{cls}",
            translation_key=translation_key,
            native_unit_of_measurement="vehicles/h",
            state_class=SensorStateClass.MEASUREMENT,
            entity_registry_enabled_default=False,
        )
        for cls, translation_key in TRAFFIC_CLASS_KEYS.items()
    ),
)

DESCRIPTIONS = {
    KIND_TEMPERATURE: TEMPERATURE_SENSORS,
    KIND_WEATHER: WEATHER_SENSORS,
    KIND_TRAFFIC: TRAFFIC_SENSORS,
}

LAST_MEASUREMENT = ReadiSensorDescription(
    key="last_measurement",
    translation_key="last_measurement",
    device_class=SensorDeviceClass.TIMESTAMP,
    entity_category=EntityCategory.DIAGNOSTIC,
)


def device_info(sensor: dict[str, Any]) -> DeviceInfo:
    """The device of a selected portal sensor."""
    return DeviceInfo(
        identifiers={(DOMAIN, device_id(sensor))},
        name=sensor["name"],
        manufacturer=sensor.get("publisher"),
        configuration_url=f"{PORTAL_URL}/dataset/{PACKAGES[sensor['kind']]}",
    )


def _descriptions_for(kind: str, values: dict[str, Any], name: str) -> list[ReadiSensorDescription]:
    """Descriptions for the values a sensor actually delivers."""
    found = [d for d in DESCRIPTIONS[kind] if d.key in values]
    if kind == KIND_TRAFFIC:
        found += [
            ReadiSensorDescription(
                key=key,
                translation_key="vehicles_direction",
                # "Rastatter Strasse - Richtung Innenstadt" -> "Richtung Innenstadt"
                translation_placeholders={
                    "direction": key.removeprefix("direction:").removeprefix(f"{name} - ")
                },
                native_unit_of_measurement="vehicles/h",
                state_class=SensorStateClass.MEASUREMENT,
                entity_registry_enabled_default=False,
            )
            for key in values
            if key.startswith("direction:")
        ]
    return found


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ReadiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create entities for every value the selected sensors deliver."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        new: list[ReadiSensor] = []
        for sensor in coordinator.sensors:
            data = (coordinator.data or {}).get(device_id(sensor))
            if data is None:
                continue
            descriptions = _descriptions_for(sensor["kind"], data.values, sensor["name"])
            for description in [*descriptions, LAST_MEASUREMENT]:
                uid = f"{device_id(sensor)}:{description.key}"
                if uid in known:
                    continue
                known.add(uid)
                primary = description.key == MAP_ENTITY[sensor["kind"]]
                new.append(ReadiSensor(coordinator, sensor, description, primary=primary))
        if new:
            async_add_entities(new)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))


class ReadiSensor(CoordinatorEntity[ReadiCoordinator], SensorEntity):
    """One value of a portal sensor."""

    _attr_has_entity_name = True
    entity_description: ReadiSensorDescription

    def __init__(
        self,
        coordinator: ReadiCoordinator,
        sensor: dict[str, Any],
        description: ReadiSensorDescription,
        primary: bool,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._sensor = sensor
        self._device_id = device_id(sensor)
        self._primary = primary
        self._attr_unique_id = f"{self._device_id}:{description.key}"
        self._attr_attribution = sensor.get("attribution")
        self._attr_device_info = device_info(sensor)

    @property
    def _data(self):
        return (self.coordinator.data or {}).get(self._device_id)

    @property
    def available(self) -> bool:
        data = self._data
        if not super().available or data is None:
            return False
        if self.entity_description.key == LAST_MEASUREMENT.key:
            return data.timestamp is not None
        return (
            is_fresh(data.timestamp, dt_util.utcnow(), MAX_AGE[self._sensor["kind"]])
            and data.values.get(self.entity_description.key) is not None
        )

    @property
    def native_value(self):
        data = self._data
        if data is None:
            return None
        if self.entity_description.key == LAST_MEASUREMENT.key:
            return data.timestamp
        return data.values.get(self.entity_description.key)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        latitude, longitude = self._sensor.get("latitude"), self._sensor.get("longitude")
        if not self._primary or latitude is None or longitude is None:
            return None
        return {ATTR_LATITUDE: latitude, ATTR_LONGITUDE: longitude}

"""Weather entity for each weather station, current values only."""

from __future__ import annotations

from typing import Any

from homeassistant.components.weather import WeatherEntity
from homeassistant.const import UnitOfPressure, UnitOfSpeed, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import KIND_WEATHER
from .coordinator import ReadiConfigEntry, ReadiCoordinator, device_id
from .parse import is_fresh
from .sensor import MAX_AGE, device_info

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ReadiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add a weather entity for every station that measures temperature."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        new = []
        for sensor in coordinator.sensors:
            if sensor["kind"] != KIND_WEATHER or device_id(sensor) in known:
                continue
            data = (coordinator.data or {}).get(device_id(sensor))
            if data is None or "temp_avg" not in data.values:
                continue
            known.add(device_id(sensor))
            new.append(ReadiWeather(coordinator, sensor))
        if new:
            async_add_entities(new)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))


class ReadiWeather(CoordinatorEntity[ReadiCoordinator], WeatherEntity):
    """Current weather at a station. The stations make no forecast."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_wind_speed_unit = UnitOfSpeed.METERS_PER_SECOND

    def __init__(self, coordinator: ReadiCoordinator, sensor: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self._device_id = device_id(sensor)
        self._attr_unique_id = f"{self._device_id}:weather"
        self._attr_attribution = sensor.get("attribution")
        self._attr_device_info = device_info(sensor)

    def _value(self, key: str) -> float | None:
        data = (self.coordinator.data or {}).get(self._device_id)
        return data.values.get(key) if data else None

    @property
    def available(self) -> bool:
        data = (self.coordinator.data or {}).get(self._device_id)
        return (
            super().available
            and data is not None
            and is_fresh(data.timestamp, dt_util.utcnow(), MAX_AGE[KIND_WEATHER])
        )

    @property
    def condition(self) -> str | None:
        """Only what the station measures: rain and lightning."""
        rain = (self._value("precip_abs_int") or 0) > 0
        lightning = (self._value("flash_minute") or 0) > 0 or (self._value("flash_interval") or 0) > 0
        if lightning:
            return "lightning-rainy" if rain else "lightning"
        if rain:
            return "rainy"
        return None

    @property
    def native_temperature(self) -> float | None:
        return self._value("temp_avg")

    @property
    def humidity(self) -> float | None:
        return self._value("rel_hum_avg")

    @property
    def native_pressure(self) -> float | None:
        return self._value("rel_press_avg")

    @property
    def native_dew_point(self) -> float | None:
        return self._value("dew_pt_avg")

    @property
    def native_wind_speed(self) -> float | None:
        return self._value("wnd_spd_avg")

    @property
    def native_wind_gust_speed(self) -> float | None:
        return self._value("wnd_spd_max")

    @property
    def wind_bearing(self) -> float | None:
        return self._value("wnd_dir_compass_corr")

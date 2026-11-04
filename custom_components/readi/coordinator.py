"""Polls the portal for all selected sensors of one city."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ReadiClient, ReadiError
from .const import CONF_SENSORS, DOMAIN, KIND_TEMPERATURE, KIND_TRAFFIC, KIND_WEATHER, TRAFFIC_RESOURCE, UPDATE_INTERVAL
from .parse import aggregate_traffic, latest_values

_LOGGER = logging.getLogger(__name__)

TEMPERATURE_FIELDS = ["temperature", "humidity"]
WEATHER_FIELDS = [
    "temp_avg", "rel_hum_avg", "rel_press_avg", "abs_press_avg", "precip_abs",
    "precip_abs_int", "wnd_spd_avg", "wnd_spd_max", "wnd_dir_compass_corr",
    "global_rad", "dew_pt_avg", "wet_bulb_temp", "windchill_temp", "air_density",
    "spec_enthalpy", "abs_hum_avg", "flash_interval", "flash_minute",
]

type ReadiConfigEntry = ConfigEntry[ReadiCoordinator]


@dataclass
class DeviceData:
    """The newest values of one portal sensor."""

    timestamp: datetime | None
    values: dict[str, float | None]


def device_id(sensor: dict[str, Any]) -> str:
    """Stable id of a selected sensor."""
    return f"{sensor['kind']}:{sensor['id']}"


class ReadiCoordinator(DataUpdateCoordinator[dict[str, DeviceData]]):
    """Fetches every selected sensor in parallel."""

    config_entry: ReadiConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ReadiConfigEntry, client: ReadiClient) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=UPDATE_INTERVAL)
        self.client = client
        self.sensors: list[dict[str, Any]] = list(entry.options.get(CONF_SENSORS, []))

    async def _fetch(self, sensor: dict[str, Any]) -> DeviceData:
        kind = sensor["kind"]
        if kind == KIND_TEMPERATURE:
            timestamp, values = latest_values(await self.client.records(sensor["id"], 5), TEMPERATURE_FIELDS)
            return DeviceData(timestamp, values)
        if kind == KIND_WEATHER:
            timestamp, values = latest_values(await self.client.records(sensor["id"], 12), WEATHER_FIELDS)
            return DeviceData(timestamp, values)
        if kind == KIND_TRAFFIC:
            records = await self.client.records(TRAFFIC_RESOURCE, 300, filters={"sensor_id": sensor["id"]})
            traffic = aggregate_traffic(records)
            if traffic is None:
                return DeviceData(None, {})
            values: dict[str, float | None] = {"total": traffic["total"], "avg_speed": traffic["avg_speed"]}
            values.update({f"class:{k}": v for k, v in traffic["classes"].items()})
            values.update({f"direction:{k}": v for k, v in traffic["directions"].items()})
            return DeviceData(traffic["timestamp"], values)
        raise ReadiError(f"Unknown sensor type {kind}")

    async def _async_update_data(self) -> dict[str, DeviceData]:
        results = await asyncio.gather(*(self._fetch(s) for s in self.sensors), return_exceptions=True)
        data: dict[str, DeviceData] = {}
        for sensor, result in zip(self.sensors, results, strict=True):
            if isinstance(result, ReadiError):
                _LOGGER.debug("Fetching %s failed: %s", sensor["name"], result)
                continue
            if isinstance(result, BaseException):
                raise result
            data[device_id(sensor)] = result
        if self.sensors and not data:
            raise UpdateFailed("Could not reach the re@di open data portal")
        return data

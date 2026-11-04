"""Tests for the weather entity of a weather station."""

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.weather import (
    ATTR_WEATHER_DEW_POINT,
    ATTR_WEATHER_HUMIDITY,
    ATTR_WEATHER_PRESSURE,
    ATTR_WEATHER_TEMPERATURE,
    ATTR_WEATHER_WIND_BEARING,
    ATTR_WEATHER_WIND_GUST_SPEED,
    ATTR_WEATHER_WIND_SPEED,
)
from homeassistant.const import ATTR_ATTRIBUTION, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.readi.const import DOMAIN, SEARCH_URL

ATTRIBUTION = "Data: Stadt Ettlingen, re@di Open Data (CC-BY-NC 4.0)"


def _station(name: str, resource_id: str) -> dict:
    return {
        "kind": "weather",
        "id": resource_id,
        "name": name,
        "latitude": None,
        "longitude": None,
        "publisher": "Stadt Ettlingen",
        "attribution": ATTRIBUTION,
    }


def _record(**values) -> dict:
    record = {
        "timestamp": "2026-11-04T20:50:01",
        "temp_avg": 6.1,
        "rel_hum_avg": 74.5,
        "rel_press_avg": 1027.9,
        "dew_pt_avg": 1.9,
        "wnd_spd_avg": 1.0,
        "wnd_spd_max": 3.6,
        "wnd_dir_compass_corr": 117,
        "precip_abs_int": 0,
        "flash_minute": 0,
    }
    record.update(values)
    return record


async def _setup(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, records: list, station=None) -> None:
    station = station or _station("Oberweier", "res-w1")
    aioclient_mock.get(
        SEARCH_URL,
        params={"resource_id": station["id"]},
        json={"success": True, "result": {"records": records}},
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="stadt-ettlingen",
        data={"city": "stadt-ettlingen"},
        options={"sensors": [station]},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.fixture(autouse=True)
def _now(freezer: FrozenDateTimeFactory) -> None:
    freezer.move_to("2026-11-04T21:00:00+00:00")


async def test_weather_entity_shows_current_values(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    await _setup(hass, aioclient_mock, [_record()])

    state = hass.states.get("weather.oberweier")
    assert state.state == STATE_UNKNOWN
    assert state.attributes[ATTR_WEATHER_TEMPERATURE] == 6.1
    assert state.attributes[ATTR_WEATHER_HUMIDITY] == 74  # weather entities round to whole percent
    assert state.attributes[ATTR_WEATHER_PRESSURE] == 1027.9
    assert state.attributes[ATTR_WEATHER_DEW_POINT] == 1.9
    assert state.attributes[ATTR_WEATHER_WIND_SPEED] == 3.6  # 1 m/s in km/h
    assert state.attributes[ATTR_WEATHER_WIND_GUST_SPEED] == 12.96
    assert state.attributes[ATTR_WEATHER_WIND_BEARING] == 117
    assert state.attributes[ATTR_ATTRIBUTION] == ATTRIBUTION


async def test_weather_skips_empty_rows(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    empty = {key: None for key in _record()} | {"timestamp": "2026-11-04T20:53:01"}
    await _setup(hass, aioclient_mock, [empty, _record()])

    assert hass.states.get("weather.oberweier").attributes[ATTR_WEATHER_TEMPERATURE] == 6.1


async def test_rain_sets_rainy(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    await _setup(hass, aioclient_mock, [_record(precip_abs_int=0.8)])

    assert hass.states.get("weather.oberweier").state == "rainy"


async def test_lightning_sets_lightning(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    await _setup(hass, aioclient_mock, [_record(flash_minute=2)])

    assert hass.states.get("weather.oberweier").state == "lightning"


async def test_lightning_and_rain_sets_lightning_rainy(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    await _setup(hass, aioclient_mock, [_record(flash_minute=2, precip_abs_int=3.1)])

    assert hass.states.get("weather.oberweier").state == "lightning-rainy"


async def test_stale_station_is_unavailable(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    await _setup(hass, aioclient_mock, [_record(timestamp="2026-11-04T17:00:00")])

    assert hass.states.get("weather.oberweier").state == STATE_UNAVAILABLE


async def test_station_without_temperature_has_no_weather_entity(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    wind_only = {"timestamp": "2026-11-04T20:50:00", "wnd_spd_avg": 2.3, "wnd_spd_max": 4.8, "wnd_dir_compass_corr": 117}
    await _setup(hass, aioclient_mock, [wind_only], station=_station("Schlauchturm", "res-w6"))

    assert hass.states.get("weather.schlauchturm") is None
    assert hass.states.get("sensor.schlauchturm_wind_speed").state == "8.28"  # 2.3 m/s in km/h

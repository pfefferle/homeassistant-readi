"""Tests for the sensors created from selected portal sensors."""

from datetime import timedelta

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import ATTR_ATTRIBUTION, ATTR_LATITUDE, ATTR_LONGITUDE, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.readi.const import DOMAIN, SEARCH_URL, TRAFFIC_RESOURCE

NOW = "2026-11-04T21:00:00+00:00"
ATTRIBUTION = "Data: Hauptamt Ettlingen, re@di Open Data (CC-BY-SA 4.0)"

TEMP = {
    "kind": "temperature",
    "id": "res-t1",
    "name": "swe-milesight-em300-0001",
    "latitude": 48.939,
    "longitude": 8.409,
    "publisher": "Hauptamt Ettlingen",
    "attribution": ATTRIBUTION,
}
WEATHER = {
    "kind": "weather",
    "id": "res-w1",
    "name": "Oberweier",
    "latitude": None,
    "longitude": None,
    "publisher": "Stadt Ettlingen",
    "attribution": "Data: Stadt Ettlingen, re@di Open Data (CC-BY-NC 4.0)",
}
TRAFFIC = {
    "kind": "traffic",
    "id": "1263",
    "name": "Rastatter Strasse",
    "latitude": 48.9402,
    "longitude": 8.4035,
    "publisher": "Ordnungsamt Ettlingen",
    "attribution": "Data: Ordnungsamt Ettlingen, re@di Open Data (CC-BY-NC 4.0)",
}


def _search(aioclient_mock: AiohttpClientMocker, params: dict, records: list) -> None:
    aioclient_mock.get(
        SEARCH_URL,
        params=params,
        json={"success": True, "result": {"records": records}},
    )


def _mock_portal(aioclient_mock: AiohttpClientMocker, temp_ts="2026-11-04T20:54:00") -> None:
    _search(
        aioclient_mock,
        {"resource_id": "res-t1"},
        [{"timestamp": temp_ts, "temperature": 5.6, "humidity": 78.5}],
    )
    _search(
        aioclient_mock,
        {"resource_id": "res-w1"},
        [
            {"timestamp": "2026-11-04T20:53:01", "temp_avg": None, "dew_pt_avg": None},
            {"timestamp": "2026-11-04T20:50:01", "temp_avg": 6.1, "dew_pt_avg": 1.9, "precip_abs": 62.45},
        ],
    )
    _search(
        aioclient_mock,
        {"resource_id": TRAFFIC_RESOURCE},
        [
            {"timestamp": "2026-11-04T20:00:00", "direction": "Richtung Innenstadt", "classification": "PKW", "y": 78, "avg_speed": 35.6},
            {"timestamp": "2026-11-04T20:00:00", "direction": "Richtung Bruchhausen", "classification": "LKW", "y": 2, "avg_speed": 30.0},
            {"timestamp": "2026-11-04T19:00:00", "direction": "Richtung Schloßgartenstraße", "classification": "PKW", "y": 29, "avg_speed": 29.6},
        ],
    )


async def _setup(hass: HomeAssistant, sensors: list[dict]) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Ettlingen",
        unique_id="stadt-ettlingen",
        data={"city": "stadt-ettlingen"},
        options={"sensors": sensors},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.fixture(autouse=True)
def _now(freezer: FrozenDateTimeFactory) -> None:
    freezer.move_to(NOW)


async def test_temperature_sensor(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    _mock_portal(aioclient_mock)
    await _setup(hass, [TEMP])

    temperature = hass.states.get("sensor.swe_milesight_em300_0001_temperature")
    assert temperature.state == "5.6"
    assert temperature.attributes["unit_of_measurement"] == "°C"
    assert temperature.attributes[ATTR_ATTRIBUTION] == ATTRIBUTION
    assert temperature.attributes[ATTR_LATITUDE] == 48.939
    assert temperature.attributes[ATTR_LONGITUDE] == 8.409
    assert hass.states.get("sensor.swe_milesight_em300_0001_humidity").state == "78.5"


async def test_only_primary_entity_is_on_the_map(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    _mock_portal(aioclient_mock)
    await _setup(hass, [TEMP])

    humidity = hass.states.get("sensor.swe_milesight_em300_0001_humidity")
    assert ATTR_LATITUDE not in humidity.attributes


async def test_device_per_selected_sensor(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, device_registry: dr.DeviceRegistry):
    _mock_portal(aioclient_mock)
    entry = await _setup(hass, [TEMP, WEATHER])

    device = device_registry.async_get_device_by_identifier((DOMAIN, "temperature:res-t1"), entry.entry_id)
    assert device.name == "swe-milesight-em300-0001"
    assert device.manufacturer == "Hauptamt Ettlingen"
    assert device_registry.async_get_device_by_identifier((DOMAIN, "weather:res-w1"), entry.entry_id)


async def test_stale_sensor_is_unavailable(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    _mock_portal(aioclient_mock, temp_ts="2026-11-04T17:00:00")
    await _setup(hass, [TEMP])

    assert hass.states.get("sensor.swe_milesight_em300_0001_temperature").state == STATE_UNAVAILABLE


async def test_weather_station_skips_empty_rows(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    _mock_portal(aioclient_mock)
    await _setup(hass, [WEATHER])

    assert hass.states.get("sensor.oberweier_temperature").state == "6.1"
    assert hass.states.get("sensor.oberweier_precipitation_total").state == "62.45"


async def test_weather_station_without_a_field_has_no_entity(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entity_registry: er.EntityRegistry):
    _mock_portal(aioclient_mock)
    await _setup(hass, [WEATHER])

    assert hass.states.get("sensor.oberweier_wind_speed") is None


async def test_weather_extras_are_disabled_by_default(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entity_registry: er.EntityRegistry):
    _mock_portal(aioclient_mock)
    await _setup(hass, [WEATHER])

    dew_point = entity_registry.async_get("sensor.oberweier_dew_point")
    assert dew_point.disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_traffic_counter(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entity_registry: er.EntityRegistry):
    _mock_portal(aioclient_mock)
    await _setup(hass, [TRAFFIC])

    assert hass.states.get("sensor.rastatter_strasse_vehicles").state == "80"
    assert hass.states.get("sensor.rastatter_strasse_average_speed").state == str(round((78 * 35.6 + 2 * 30.0) / 80, 1))
    cars = entity_registry.async_get("sensor.rastatter_strasse_cars")
    assert cars.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    direction = entity_registry.async_get("sensor.rastatter_strasse_vehicles_richtung_schlossgartenstrasse")
    assert direction.disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_traffic_direction_name_drops_the_location(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entity_registry: er.EntityRegistry):
    _search(
        aioclient_mock,
        {"resource_id": TRAFFIC_RESOURCE},
        [{"timestamp": "2026-11-04T20:00:00", "direction": "Rastatter Strasse - Richtung Innenstadt", "classification": "PKW", "y": 5, "avg_speed": 30.0}],
    )
    await _setup(hass, [TRAFFIC])

    assert entity_registry.async_get("sensor.rastatter_strasse_vehicles_richtung_innenstadt")


async def test_traffic_request_filters_by_counter(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    _mock_portal(aioclient_mock)
    await _setup(hass, [TRAFFIC])

    _, url, _, _ = aioclient_mock.mock_calls[-1]
    assert '"sensor_id": "1263"' in url.query["filters"]


async def test_failed_request_marks_only_that_device_unavailable(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    aioclient_mock.get(SEARCH_URL, params={"resource_id": "res-w1"}, status=500)
    _search(aioclient_mock, {"resource_id": "res-t1"}, [{"timestamp": "2026-11-04T20:54:00", "temperature": 5.6, "humidity": 78.5}])
    await _setup(hass, [TEMP, WEATHER])

    assert hass.states.get("sensor.swe_milesight_em300_0001_temperature").state == "5.6"
    assert hass.states.get("sensor.oberweier_temperature") is None or hass.states.get("sensor.oberweier_temperature").state == STATE_UNAVAILABLE


async def test_values_refresh(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory):
    _mock_portal(aioclient_mock)
    await _setup(hass, [TEMP])
    aioclient_mock.clear_requests()
    _search(aioclient_mock, {"resource_id": "res-t1"}, [{"timestamp": "2026-11-04T21:05:00", "temperature": 4.9, "humidity": 80.0}])

    freezer.tick(timedelta(minutes=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert hass.states.get("sensor.swe_milesight_em300_0001_temperature").state == "4.9"


async def test_map_position_stays_on_main_entity_when_first_poll_is_empty(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory):
    _search(aioclient_mock, {"resource_id": TRAFFIC_RESOURCE}, [])
    await _setup(hass, [TRAFFIC])
    aioclient_mock.clear_requests()
    _search(
        aioclient_mock,
        {"resource_id": TRAFFIC_RESOURCE},
        [{"timestamp": "2026-11-04T20:00:00", "direction": "Richtung Innenstadt", "classification": "PKW", "y": 5, "avg_speed": 30.0}],
    )

    freezer.tick(timedelta(minutes=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert hass.states.get("sensor.rastatter_strasse_vehicles").attributes[ATTR_LATITUDE] == 48.9402
    assert ATTR_LATITUDE not in hass.states.get("sensor.rastatter_strasse_last_measurement").attributes

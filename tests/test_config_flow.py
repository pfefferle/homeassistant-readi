"""Tests for adding a city and choosing sensors."""

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.readi.const import (
    DOMAIN,
    PACKAGE_URL,
    SEARCH_URL,
    TEMPERATURE_LOCATIONS,
    TEMPERATURE_PACKAGE,
    TRAFFIC_PACKAGE,
    TRAFFIC_RESOURCE,
    WEATHER_PACKAGE,
)


def _package(name, author, license_id, resources):
    return {
        "name": name,
        "author": author,
        "license_id": license_id,
        "license_title": "Some licence",
        "resources": resources,
    }


def _mock_catalog(aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(
        PACKAGE_URL,
        params={"id": TEMPERATURE_PACKAGE},
        json={"success": True, "result": _package(
            TEMPERATURE_PACKAGE, "Hauptamt Ettlingen", "http://dcat-ap.de/def/licenses/cc-by-sa/4.0",
            [
                {"id": TEMPERATURE_LOCATIONS, "name": "Sensor Standorte", "datastore_active": True},
                {"id": "res-near", "name": "swe-milesight-em300-0001", "datastore_active": True},
                {"id": "res-far", "name": "swe-milesight-em300-0002", "datastore_active": True},
                {"id": "res-nowhere", "name": "swe-milesight-em300-0099", "datastore_active": True},
            ],
        )},
    )
    aioclient_mock.get(
        PACKAGE_URL,
        params={"id": WEATHER_PACKAGE},
        json={"success": True, "result": _package(
            WEATHER_PACKAGE, "Stadt Ettlingen", "http://dcat-ap.de/def/licenses/cc-by-nc/4.0",
            [
                {"id": "html", "name": "Wetterdaten live", "datastore_active": False},
                {"id": "res-ober", "name": "Wetterstation Oberweier", "datastore_active": True},
            ],
        )},
    )
    aioclient_mock.get(
        PACKAGE_URL,
        params={"id": TRAFFIC_PACKAGE},
        json={"success": True, "result": _package(
            TRAFFIC_PACKAGE, "Ordnungsamt Ettlingen", "http://dcat-ap.de/def/licenses/cc-by-nc/4.0",
            [{"id": TRAFFIC_RESOURCE, "name": "Stundenwerte", "datastore_active": True}],
        )},
    )
    aioclient_mock.get(
        SEARCH_URL,
        params={"resource_id": TEMPERATURE_LOCATIONS},
        json={"success": True, "result": {"records": [
            {"sensor_id": "swe-milesight-em300-0001", "latitude": 48.9401, "longitude": 8.4001},
            {"sensor_id": "swe-milesight-em300-0002", "latitude": 48.9600, "longitude": 8.4300},
        ]}},
    )
    aioclient_mock.get(
        SEARCH_URL,
        params={"resource_id": TRAFFIC_RESOURCE},
        json={"success": True, "result": {"records": [
            {"sensor_id": "1263", "label": "Rastatter Strasse", "latitude": 48.9402, "longitude": 8.4035},
            {"sensor_id": "1263", "label": "Rastatter Strasse", "latitude": 48.9402, "longitude": 8.4035},
            {"sensor_id": "395842", "label": "Karlsruher Strasse", "latitude": 48.9563, "longitude": 8.4064},
        ]}},
    )


def _home(hass: HomeAssistant) -> None:
    hass.states.async_set(
        "zone.home", "0", {"latitude": 48.9400, "longitude": 8.4000, "radius": 100, "friendly_name": "Home"}
    )


def _field(result, name):
    for key, selector in result["data_schema"].schema.items():
        if key == name:
            return key, selector
    raise AssertionError(f"{name} not in form")


def _default(result, name):
    key, _ = _field(result, name)
    return key.default()


def _labels(result, name):
    _, selector = _field(result, name)
    return [option["label"] for option in selector.config["options"]]


async def test_single_city_goes_straight_to_sensors(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    _home(hass)
    _mock_catalog(aioclient_mock)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "sensors"


async def test_nearest_sensors_are_preselected(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    _home(hass)
    _mock_catalog(aioclient_mock)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    assert _default(result, "temperature") == ["res-near"]
    assert _default(result, "traffic") == ["1263"]
    assert _default(result, "weather") == []


async def test_options_sorted_by_distance_with_zone_in_label(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    _home(hass)
    _mock_catalog(aioclient_mock)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    assert _labels(result, "temperature") == [
        "swe-milesight-em300-0001 · 0.0 km from Home",
        "swe-milesight-em300-0002 · 3.0 km from Home",
        "swe-milesight-em300-0099",
    ]
    assert _labels(result, "weather") == ["Oberweier"]


async def test_creates_entry_with_selected_sensors(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    _home(hass)
    _mock_catalog(aioclient_mock)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"temperature": ["res-near"], "weather": ["res-ober"], "traffic": []}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Ettlingen"
    assert result["data"] == {"city": "stadt-ettlingen"}
    assert result["options"]["sensors"] == [
        {
            "kind": "temperature",
            "id": "res-near",
            "name": "swe-milesight-em300-0001",
            "latitude": 48.9401,
            "longitude": 8.4001,
            "publisher": "Hauptamt Ettlingen",
            "attribution": "Data: Hauptamt Ettlingen, re@di Open Data (CC-BY-SA 4.0)",
        },
        {
            "kind": "weather",
            "id": "res-ober",
            "name": "Oberweier",
            "latitude": None,
            "longitude": None,
            "publisher": "Stadt Ettlingen",
            "attribution": "Data: Stadt Ettlingen, re@di Open Data (CC-BY-NC 4.0)",
        },
    ]


async def test_city_can_only_be_added_once(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    MockConfigEntry(domain=DOMAIN, unique_id="stadt-ettlingen", data={"city": "stadt-ettlingen"}).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_portal_unreachable(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    aioclient_mock.get(PACKAGE_URL, status=503)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_options_flow_changes_selection(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    _home(hass)
    _mock_catalog(aioclient_mock)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="stadt-ettlingen",
        data={"city": "stadt-ettlingen"},
        options={"sensors": [{"kind": "traffic", "id": "395842", "name": "Karlsruher Strasse", "latitude": None, "longitude": None, "publisher": None, "attribution": None}]},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert _default(result, "traffic") == ["395842"]
    assert _default(result, "temperature") == []

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"temperature": ["res-far"], "weather": [], "traffic": []}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert [s["id"] for s in entry.options["sensors"]] == ["res-far"]


async def test_options_flow_keeps_sensors_missing_from_the_catalog(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    _mock_catalog(aioclient_mock)
    offline = {"kind": "traffic", "id": "386119", "name": "Schillerstraße 2-4", "latitude": 48.94, "longitude": 8.40, "publisher": "Ordnungsamt Ettlingen", "attribution": "x"}
    entry = MockConfigEntry(domain=DOMAIN, unique_id="stadt-ettlingen", data={"city": "stadt-ettlingen"}, options={"sensors": [offline]})
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert _default(result, "traffic") == ["386119"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"temperature": [], "weather": [], "traffic": ["386119"]}
    )

    assert entry.options["sensors"] == [offline]

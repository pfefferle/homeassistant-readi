"""Constants for the re@di Open Data integration."""

from datetime import timedelta

DOMAIN = "readi"

PORTAL_URL = "https://opendata.readi.de"
SEARCH_URL = f"{PORTAL_URL}/api/3/action/datastore_search"
PACKAGE_URL = f"{PORTAL_URL}/api/3/action/package_show"

UPDATE_INTERVAL = timedelta(minutes=10)

CONF_CITY = "city"
CONF_SENSORS = "sensors"

KIND_TEMPERATURE = "temperature"
KIND_WEATHER = "weather"
KIND_TRAFFIC = "traffic"
KINDS = (KIND_TEMPERATURE, KIND_WEATHER, KIND_TRAFFIC)

# Ettlingen
TEMPERATURE_PACKAGE = "temperatursensoren"
TEMPERATURE_LOCATIONS = "07c2d733-5106-43d2-bc45-084f12a66606"
WEATHER_PACKAGE = "wetterstationen-ettlingen"
TRAFFIC_PACKAGE = "automatisierte-verkehrszahlung-in-ettlingen"
TRAFFIC_RESOURCE = "a903967d-9177-4db6-977c-267fd745a390"

# Station positions are not published in the portal yet. Fill in as
# resource id -> (latitude, longitude) once known.
WEATHER_STATION_COORDINATES: dict[str, tuple[float, float]] = {}

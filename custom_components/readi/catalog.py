"""Sort and preselect sensors by the user's zones."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from typing import Any

from homeassistant.util.location import distance

from .api import ReadiClient
from .const import (
    KIND_TEMPERATURE,
    KIND_TRAFFIC,
    KIND_WEATHER,
    TEMPERATURE_LOCATIONS,
    TEMPERATURE_PACKAGE,
    TRAFFIC_PACKAGE,
    TRAFFIC_RESOURCE,
    WEATHER_PACKAGE,
    WEATHER_STATION_COORDINATES,
)

MAX_PRESELECT_KM = 3.0


@dataclass(frozen=True)
class Candidate:
    """A sensor the user can pick."""

    id: str
    kind: str
    name: str
    latitude: float | None = None
    longitude: float | None = None


@dataclass(frozen=True)
class Zone:
    """A Home Assistant zone."""

    name: str
    latitude: float
    longitude: float
    radius: float  # metres


def nearest_zone(candidate: Candidate, zones: list[Zone]) -> tuple[str, float] | None:
    """Return the closest zone and the distance in km from its edge."""
    if candidate.latitude is None or candidate.longitude is None or not zones:
        return None
    best: tuple[str, float] | None = None
    for zone in zones:
        metres = distance(zone.latitude, zone.longitude, candidate.latitude, candidate.longitude)
        km = max(0.0, (metres or 0) - zone.radius) / 1000
        if best is None or km < best[1]:
            best = (zone.name, km)
    return best


def preselect(
    candidates: list[Candidate], zones: list[Zone], max_km: float = MAX_PRESELECT_KM
) -> set[str]:
    """Pick the nearest sensor of each kind for every zone close enough."""
    selected: set[str] = set()
    kinds = {c.kind for c in candidates}
    for zone in zones:
        for kind in kinds:
            ranked = [
                (found[1], c.id)
                for c in candidates
                if c.kind == kind and (found := nearest_zone(c, [zone])) is not None
            ]
            if ranked:
                km, cid = min(ranked)
                if km <= max_km:
                    selected.add(cid)
    return selected


def sort_candidates(candidates: list[Candidate], zones: list[Zone]) -> list[Candidate]:
    """Located sensors by distance first, then the rest by name."""

    def key(c: Candidate) -> tuple[int, float, str]:
        found = nearest_zone(c, zones)
        return (0, found[1], c.name) if found else (1, 0.0, c.name)

    return sorted(candidates, key=key)


def _license(package: dict[str, Any]) -> str:
    """'http://dcat-ap.de/def/licenses/cc-by-nc/4.0' -> 'CC-BY-NC 4.0'."""
    parts = (package.get("license_id") or "").rstrip("/").split("/")
    if len(parts) >= 2 and parts[-2].startswith("cc"):
        return f"{parts[-2].upper()} {parts[-1]}"
    return package.get("license_title") or "unknown licence"


def _source(package: dict[str, Any]) -> dict[str, str | None]:
    publisher = package.get("author")
    return {
        "publisher": publisher,
        "attribution": f"Data: {publisher}, re@di Open Data ({_license(package)})",
    }


def _datastore(package: dict[str, Any], prefix: str) -> list[dict[str, Any]]:
    return [
        r for r in package.get("resources", [])
        if r.get("datastore_active") and (r.get("name") or "").startswith(prefix)
    ]


async def fetch_sensors(client: ReadiClient) -> list[dict[str, Any]]:
    """All sensors of Ettlingen the user can pick, as stored in the entry."""
    temperature, weather, traffic, locations, traffic_rows = await asyncio.gather(
        client.package(TEMPERATURE_PACKAGE),
        client.package(WEATHER_PACKAGE),
        client.package(TRAFFIC_PACKAGE),
        client.records(TEMPERATURE_LOCATIONS, 1000, sort=None),
        client.records(
            TRAFFIC_RESOURCE, 1000, fields=["sensor_id", "label", "latitude", "longitude"]
        ),
    )

    sensors: list[dict[str, Any]] = []

    positions = {r.get("sensor_id"): (r.get("latitude"), r.get("longitude")) for r in locations}
    for resource in _datastore(temperature, "swe-"):
        lat, lon = positions.get(resource["name"], (None, None))
        sensors.append({
            **asdict(Candidate(resource["id"], KIND_TEMPERATURE, resource["name"], lat, lon)),
            **_source(temperature),
        })

    for resource in _datastore(weather, "Wetterstation "):
        lat, lon = WEATHER_STATION_COORDINATES.get(resource["id"], (None, None))
        name = resource["name"].removeprefix("Wetterstation ")
        sensors.append({
            **asdict(Candidate(resource["id"], KIND_WEATHER, name, lat, lon)),
            **_source(weather),
        })

    counters: dict[str, dict[str, Any]] = {}
    for row in traffic_rows:  # newest first, so the current label wins
        if row.get("sensor_id") and row["sensor_id"] not in counters:
            counters[row["sensor_id"]] = row
    for counter_id, row in counters.items():
        sensors.append({
            **asdict(Candidate(counter_id, KIND_TRAFFIC, row.get("label") or counter_id, row.get("latitude"), row.get("longitude"))),
            **_source(traffic),
        })

    return sensors


def candidate(sensor: dict[str, Any]) -> Candidate:
    """The Candidate of a stored sensor."""
    return Candidate(sensor["id"], sensor["kind"], sensor["name"], sensor.get("latitude"), sensor.get("longitude"))

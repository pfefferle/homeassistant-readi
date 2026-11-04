"""Add a city and choose its sensors."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import ReadiClient, ReadiError
from .catalog import Zone, candidate, fetch_sensors, nearest_zone, preselect, sort_candidates
from .const import CONF_CITY, CONF_SENSORS, DOMAIN, KINDS
from .coordinator import ReadiConfigEntry

# Cities with known live sensor data. Only Ettlingen publishes some so far.
CITIES = {"stadt-ettlingen": "Ettlingen"}


def _zones(hass: HomeAssistant) -> list[Zone]:
    zones = []
    for state in hass.states.async_all("zone"):
        lat, lon = state.attributes.get("latitude"), state.attributes.get("longitude")
        if lat is None or lon is None:
            continue
        zones.append(Zone(state.name, lat, lon, state.attributes.get("radius", 0)))
    return zones


def _label(sensor: dict[str, Any], zones: list[Zone]) -> str:
    found = nearest_zone(candidate(sensor), zones)
    if found is None:
        return sensor["name"]
    zone, km = found
    return f"{sensor['name']} · {km:.1f} km from {zone}"


def _schema(sensors: list[dict[str, Any]], zones: list[Zone], selected: set[str]) -> vol.Schema:
    by_id = {s["id"]: s for s in sensors}
    ordered = [by_id[c.id] for c in sort_candidates([candidate(s) for s in sensors], zones)]
    fields = {}
    for kind in KINDS:
        options = [
            SelectOptionDict(value=s["id"], label=_label(s, zones))
            for s in ordered
            if s["kind"] == kind
        ]
        defaults = [o["value"] for o in options if o["value"] in selected]
        fields[vol.Optional(kind, default=defaults)] = SelectSelector(
            SelectSelectorConfig(options=options, multiple=True, mode=SelectSelectorMode.DROPDOWN)
        )
    return vol.Schema(fields)


def _chosen(sensors: list[dict[str, Any]], user_input: dict[str, Any]) -> list[dict[str, Any]]:
    wanted = {(kind, sid) for kind in KINDS for sid in user_input.get(kind, [])}
    return [s for s in sensors if (s["kind"], s["id"]) in wanted]


class ReadiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up one city."""

    VERSION = 1

    def __init__(self) -> None:
        self._city: str | None = None
        self._sensors: list[dict[str, Any]] | None = None

    @staticmethod
    @callback
    def async_get_options_flow(entry: ReadiConfigEntry) -> ReadiOptionsFlow:
        return ReadiOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        configured = {e.unique_id for e in self._async_current_entries(include_ignore=False)}
        available = {k: v for k, v in CITIES.items() if k not in configured}
        if not available:
            return self.async_abort(reason="already_configured")

        if user_input is None and len(available) > 1:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({
                    vol.Required(CONF_CITY, default=next(iter(available))): SelectSelector(
                        SelectSelectorConfig(
                            options=[SelectOptionDict(value=k, label=v) for k, v in available.items()],
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }),
            )

        self._city = user_input[CONF_CITY] if user_input else next(iter(available))
        await self.async_set_unique_id(self._city)
        self._abort_if_unique_id_configured()
        return await self.async_step_sensors()

    async def async_step_sensors(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if self._sensors is None:
            try:
                self._sensors = await fetch_sensors(ReadiClient(async_get_clientsession(self.hass)))
            except ReadiError:
                return self.async_abort(reason="cannot_connect")

        if user_input is not None:
            return self.async_create_entry(
                title=CITIES[self._city],
                data={CONF_CITY: self._city},
                options={CONF_SENSORS: _chosen(self._sensors, user_input)},
            )

        zones = _zones(self.hass)
        selected = preselect([candidate(s) for s in self._sensors], zones)
        return self.async_show_form(step_id="sensors", data_schema=_schema(self._sensors, zones, selected))


class ReadiOptionsFlow(OptionsFlow):
    """Change the sensors of a city."""

    def __init__(self) -> None:
        self._sensors: list[dict[str, Any]] | None = None

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if self._sensors is None:
            stored = list(self.config_entry.options.get(CONF_SENSORS, []))
            try:
                fetched = await fetch_sensors(ReadiClient(async_get_clientsession(self.hass)))
            except ReadiError:
                errors["base"] = "cannot_connect"
                fetched = []
            # Keep selected sensors the portal currently does not list, e.g. a
            # traffic counter that has been offline for a day.
            known = {(s["kind"], s["id"]) for s in fetched}
            self._sensors = fetched + [s for s in stored if (s["kind"], s["id"]) not in known]

        if user_input is not None:
            return self.async_create_entry(data={CONF_SENSORS: _chosen(self._sensors, user_input)})

        current = {s["id"] for s in self.config_entry.options.get(CONF_SENSORS, [])}
        return self.async_show_form(
            step_id="init",
            data_schema=_schema(self._sensors, _zones(self.hass), current),
            errors=errors,
        )

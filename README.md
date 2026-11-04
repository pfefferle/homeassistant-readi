# re@di Open Data for Home Assistant

> **Community project.** This integration is not made, endorsed or supported by
> re@di, bächle & spree or the City of Ettlingen. It only reads the public
> [re@di open data portal](https://opendata.readi.de/). Please report problems
> here, not to the city.

Brings the live sensor data that the re@di cities publish into Home Assistant:

| Type | What you get | Updated |
|---|---|---|
| Temperature sensors (about 110 LoRaWAN sensors in Ettlingen) | Temperature, humidity | every few minutes |
| Weather stations (Ettlingen) | A weather entity with the current values (no forecast, the condition only shows rain and lightning), plus sensors for temperature, humidity, pressure, rain, wind, gusts, wind direction, global radiation; more values disabled by default | every 10 minutes |
| Traffic counters (Ettlingen) | Vehicles per hour, average speed; per vehicle class and per direction disabled by default | hourly, about one hour behind |

So far only Ettlingen publishes live sensor data. Other re@di cities are added
once they do.

## Installation

1. In Home Assistant, open **Settings → Marketplace**, search for
   **re@di Open Data** and install it. Until it is listed, add this repository
   as a custom repository first.
2. Restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration → re@di Open Data**.

## Setup

You pick the sensors from one dropdown per type. They are sorted by distance to
your nearest [zone](https://www.home-assistant.io/integrations/zone/), and for
every zone within 3 km the nearest sensor of each type is already selected.
Change the selection any time under **Configure**.

Every selected sensor becomes a device. Its main entity carries the sensor's
coordinates, so it shows up on the map. A sensor that stops reporting is shown
as unavailable instead of keeping its last value.

## Data and licences

All data comes from [opendata.readi.de](https://opendata.readi.de/). Each
entity names its source and licence in its attribution, for example
`Data: Stadt Ettlingen, re@di Open Data (CC-BY-NC 4.0)`. The weather and
traffic data are licensed for non-commercial use only.

The re@di logo belongs to re@di and is used only to identify the data source.

## Known limitations

- The portal publishes no coordinates for the weather stations yet, so they are
  listed after the other sensors and are never preselected.
- The fine dust sensors and the pollen data have not been updated since
  August 2026 and are not included.

## Development

```bash
python3.14 -m venv .venv
.venv/bin/pip install pytest-homeassistant-custom-component
.venv/bin/pytest
```

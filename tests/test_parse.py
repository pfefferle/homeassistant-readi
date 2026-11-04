"""Tests for the portal data parsing."""

from datetime import UTC, datetime, timedelta

from custom_components.readi.parse import (
    aggregate_traffic,
    is_fresh,
    latest_values,
    parse_timestamp,
)


def test_parse_timestamp_treats_naive_values_as_utc():
    assert parse_timestamp("2026-11-04T20:50:00") == datetime(
        2026, 11, 4, 20, 50, tzinfo=UTC
    )


def test_parse_timestamp_accepts_offset_and_space_separator():
    assert parse_timestamp("2026-08-21T00:00:00+00:00") == datetime(
        2026, 8, 21, tzinfo=UTC
    )
    assert parse_timestamp("2024-07-29 23:55:54") == datetime(
        2024, 7, 29, 23, 55, 54, tzinfo=UTC
    )


def test_parse_timestamp_returns_none_for_garbage():
    assert parse_timestamp(None) is None
    assert parse_timestamp("Sonntag, 20. Oktober 2024") is None


def test_latest_values_skips_empty_rows():
    records = [
        {"timestamp": "2026-11-04T15:53:01", "temp_avg": None, "rel_hum_avg": None},
        {"timestamp": "2026-11-04T15:50:01", "temp_avg": 6.1, "rel_hum_avg": 74.5},
    ]

    timestamp, values = latest_values(records, ["temp_avg", "rel_hum_avg"])

    assert timestamp == datetime(2026, 11, 4, 15, 50, 1, tzinfo=UTC)
    assert values == {"temp_avg": 6.1, "rel_hum_avg": 74.5}


def test_latest_values_takes_newest_value_per_field():
    records = [
        {"timestamp": "2026-11-04T21:00:00", "temp_avg": 5.0, "global_rad": None},
        {"timestamp": "2026-11-04T20:50:00", "temp_avg": 6.0, "global_rad": 12.0},
    ]

    _, values = latest_values(records, ["temp_avg", "global_rad"])

    assert values == {"temp_avg": 5.0, "global_rad": 12.0}


def test_latest_values_converts_numeric_strings():
    records = [{"timestamp": "2026-08-21T00:00:00+00:00", "pm10": "3.48"}]

    _, values = latest_values(records, ["pm10"])

    assert values == {"pm10": 3.48}


def test_latest_values_without_data():
    assert latest_values([], ["temp_avg"]) == (None, {})


def _traffic(ts, direction, cls, count, speed):
    return {
        "timestamp": ts,
        "direction": direction,
        "classification": cls,
        "y": count,
        "avg_speed": speed,
    }


def test_aggregate_traffic_sums_latest_hour():
    records = [
        _traffic("2026-11-04T20:00:00", "Richtung Karlsruhe", "PKW", 56, 72.0),
        _traffic("2026-11-04T20:00:00", "Richtung Karlsruhe", "LKW", 4, 70.0),
        _traffic("2026-11-04T20:00:00", "Richtung Ettlingen", "PKW", 40, 60.0),
        _traffic("2026-11-04T19:00:00", "Richtung Ettlingen", "PKW", 999, 10.0),
    ]

    result = aggregate_traffic(records)

    assert result["timestamp"] == datetime(2026, 11, 4, 20, tzinfo=UTC)
    assert result["total"] == 100
    assert result["avg_speed"] == round((56 * 72 + 4 * 70 + 40 * 60) / 100, 1)
    assert result["classes"]["PKW"] == 96
    assert result["classes"]["LKW"] == 4
    assert result["classes"]["Motorrad"] == 0
    assert result["directions"] == {
        "Richtung Karlsruhe": 60,
        "Richtung Ettlingen": 40,
    }


def test_aggregate_traffic_keeps_quiet_directions_at_zero():
    records = [
        _traffic("2026-11-04T20:00:00", "Richtung Karlsruhe", "PKW", 3, 50.0),
        _traffic("2026-11-04T19:00:00", "Richtung Ettlingen", "PKW", 5, 50.0),
    ]

    result = aggregate_traffic(records)

    assert result["directions"] == {"Richtung Karlsruhe": 3, "Richtung Ettlingen": 0}


def test_aggregate_traffic_without_data():
    assert aggregate_traffic([]) is None


def test_is_fresh():
    now = datetime(2026, 11, 4, 21, 0, tzinfo=UTC)
    max_age = timedelta(hours=2)

    assert is_fresh(now - timedelta(minutes=30), now, max_age)
    assert not is_fresh(now - timedelta(hours=3), now, max_age)
    assert not is_fresh(None, now, max_age)

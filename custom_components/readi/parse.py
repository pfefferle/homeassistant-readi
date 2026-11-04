"""Turn raw portal records into values."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

TRAFFIC_CLASSES = ("PKW", "LKW", "LKW+Anhänger", "Leichtes Nutzfahrzeug", "Motorrad")


def parse_timestamp(value: Any) -> datetime | None:
    """Parse a portal timestamp. Values without offset are UTC."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def latest_values(
    records: list[dict[str, Any]], fields: list[str]
) -> tuple[datetime | None, dict[str, float]]:
    """Return the newest non-empty value of each field.

    Records must be sorted newest first. The timestamp is the one of the
    newest record that carried any value.
    """
    timestamp: datetime | None = None
    values: dict[str, float] = {}
    for record in records:
        for field in fields:
            if field in values:
                continue
            number = _number(record.get(field))
            if number is None:
                continue
            values[field] = number
            if timestamp is None:
                timestamp = parse_timestamp(record.get("timestamp"))
        if len(values) == len(fields):
            break
    return timestamp, values


def aggregate_traffic(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Sum the newest hour of one traffic counter."""
    if not records:
        return None
    newest = max(records, key=lambda r: parse_timestamp(r.get("timestamp")) or datetime.min.replace(tzinfo=UTC))
    timestamp = parse_timestamp(newest.get("timestamp"))

    directions: dict[str, int] = {}
    for record in records:
        if record.get("direction"):
            directions.setdefault(record["direction"], 0)

    classes = dict.fromkeys(TRAFFIC_CLASSES, 0)
    total = 0
    speed_sum = 0.0
    for record in records:
        if parse_timestamp(record.get("timestamp")) != timestamp:
            continue
        count = int(_number(record.get("y")) or 0)
        total += count
        speed_sum += count * (_number(record.get("avg_speed")) or 0)
        classes[record.get("classification")] = classes.get(record.get("classification"), 0) + count
        if record.get("direction"):
            directions[record["direction"]] += count

    return {
        "timestamp": timestamp,
        "total": total,
        "avg_speed": round(speed_sum / total, 1) if total else None,
        "classes": classes,
        "directions": directions,
    }


def is_fresh(timestamp: datetime | None, now: datetime, max_age: timedelta) -> bool:
    """Whether a measurement is recent enough to be shown."""
    return timestamp is not None and now - timestamp <= max_age

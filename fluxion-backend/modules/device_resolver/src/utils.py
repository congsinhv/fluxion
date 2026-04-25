"""Shared helpers for device_resolver."""

from __future__ import annotations

from datetime import date


def to_iso(value: object) -> str | None:
    """Convert datetime or str to ISO-8601 with T separator, or None.

    psycopg3 returns real datetime objects; AppSync AWSDateTime requires the
    T separator — str(datetime) uses a space instead. Call .isoformat() directly.
    """
    if value is None:
        return None
    if isinstance(value, date):  # covers datetime (subclass) and date
        return value.isoformat()
    return str(value)

"""Business time helpers for the Titri P0 static pipeline."""
from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

MOSCOW = ZoneInfo("Europe/Moscow")


def now_moscow() -> datetime:
    return datetime.now(MOSCOW)


def today_moscow() -> date:
    return now_moscow().date()


def parse_local_date(value: str | None) -> date | None:
    """Parse a date-only release value without inventing a UTC timestamp."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def relative_day(value: str | None, current: date | None = None) -> str | None:
    released = parse_local_date(value)
    if not released:
        return None
    current = current or today_moscow()
    delta = (released - current).days
    if delta == 0:
        return "сегодня"
    if delta == 1:
        return "завтра"
    if delta == 2:
        return "послезавтра"
    return None

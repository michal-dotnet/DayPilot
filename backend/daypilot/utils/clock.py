"""
שעון ואזור זמן.

כל הקוד מקבל את "עכשיו" דרך Clock ולא קורא ל-datetime.now() ישירות.
כך אפשר לבדוק מעבר לשעון קיץ, ערב שבת וכדומה בלי לחכות להם.

כלל: בזיכרון ובמסד כל הזמנים הם aware ב-UTC.
המרה לשעון מקומי (Asia/Jerusalem) נעשית רק לחישוב חלונות ולהצגה.
"""

from datetime import date, datetime, time, timezone
from functools import lru_cache
from typing import Protocol
from zoneinfo import ZoneInfo

DEFAULT_TZ_NAME = "Asia/Jerusalem"


@lru_cache
def get_tz(name: str = DEFAULT_TZ_NAME) -> ZoneInfo:
    return ZoneInfo(name)


class Clock(Protocol):
    def now(self) -> datetime:  # aware, UTC
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FixedClock:
    """שעון קבוע לבדיקות. אפשר לקדם אותו ידנית."""

    def __init__(self, at: datetime):
        if at.tzinfo is None:
            raise ValueError("FixedClock requires an aware datetime")
        self._now = at.astimezone(timezone.utc)

    def now(self) -> datetime:
        return self._now

    def set(self, at: datetime) -> None:
        self._now = at.astimezone(timezone.utc)


def ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("naive datetime is not allowed; attach a timezone first")
    return dt.astimezone(timezone.utc)


def to_local(dt: datetime, tz_name: str = DEFAULT_TZ_NAME) -> datetime:
    return ensure_utc(dt).astimezone(get_tz(tz_name))


def local_datetime(d: date, t: time, tz_name: str = DEFAULT_TZ_NAME) -> datetime:
    """יוצר datetime מקומי aware (zoneinfo מטפל בשעון קיץ/חורף)."""
    return datetime.combine(d, t, tzinfo=get_tz(tz_name))


def local_today(clock: Clock, tz_name: str = DEFAULT_TZ_NAME) -> date:
    return to_local(clock.now(), tz_name).date()

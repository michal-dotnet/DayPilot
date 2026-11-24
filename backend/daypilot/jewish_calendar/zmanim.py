"""
שקיעה וצאת הכוכבים לעיר ותאריך, באמצעות hdate.

כל השימוש ב-hdate מרוכז כאן, כדי שעדכון גרסה של הספרייה ישפיע על קובץ אחד בלבד.
"""

from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache

import hdate

from daypilot.jewish_calendar.cities import CityInfo
from daypilot.utils.clock import get_tz


@lru_cache(maxsize=64)
def _location(city: CityInfo, tz_name: str) -> hdate.Location:
    return hdate.Location(
        name=city.name_en,
        latitude=city.latitude,
        longitude=city.longitude,
        timezone=tz_name,
        altitude=city.altitude,
        diaspora=False,
    )


@lru_cache(maxsize=4096)
def _zmanim(d: date, city: CityInfo, tz_name: str) -> hdate.Zmanim:
    return hdate.Zmanim(date=d, location=_location(city, tz_name))


def _aware(value: datetime, tz_name: str) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=get_tz(tz_name))
    return value


def sunset(d: date, city: CityInfo, tz_name: str) -> datetime:
    return _aware(_zmanim(d, city, tz_name).shkia.local, tz_name)


def nightfall(d: date, city: CityInfo, tz_name: str) -> datetime:
    """צאת הכוכבים (סוף שבת/חג)."""
    return _aware(_zmanim(d, city, tz_name).tset_hakohavim.local, tz_name)

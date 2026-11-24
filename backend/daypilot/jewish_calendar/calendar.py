"""
לוח עברי: תאריכים, חגים וזמני שבת.

- תאריכים עבריים וחגים (לוח ארץ ישראל): pyluach.
- שקיעה וצאת הכוכבים לפי מיקום העיר: hdate.

החישוב של זמנים חסומים לשיבוץ:
- רצף ימי מנוחה (שבת ו/או יום טוב, כולל חג שצמוד לשבת) נחסם כבלוק אחד:
  מ-(הדלקת נרות של ערב הרצף פחות מרווח שהמשתמשת בחרה) ועד צאת היום האחרון.
- חול המועד נחסם לפי היום העברי (מצאת הכוכבים של הערב הקודם ועד צאת הכוכבים), אם הוגדר כך.
  כך חג, חול המועד והחג שאחריו מתחברים לבלוק רציף אחד.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache

from pyluach import dates as pl_dates
from pyluach import hebrewcal

from daypilot.domain.intervals import Interval, normalize
from daypilot.jewish_calendar import zmanim
from daypilot.jewish_calendar.cities import CityInfo

YOM_TOV_NAMES = {"Rosh Hashana", "Yom Kippur", "Succos", "Shmini Atzeres", "Pesach", "Shavuos"}
CHOL_HAMOED_FESTIVALS = {"Succos", "Pesach"}


@dataclass(frozen=True)
class DayInfo:
    day: date
    hebrew_date: str  # בעברית, למשל: ט״ו שבט תשפ״ז
    holiday: str | None  # שם החג בעברית, אם יש
    is_shabbat: bool
    is_yom_tov: bool
    is_chol_hamoed: bool

    @property
    def is_rest_day(self) -> bool:
        return self.is_shabbat or self.is_yom_tov


@lru_cache(maxsize=4096)
def day_info(d: date) -> DayInfo:
    g = pl_dates.GregorianDate.from_pydate(d)
    h = g.to_heb()
    yom_tov_name = hebrewcal.festival(h, israel=True, include_working_days=False)
    any_name = hebrewcal.festival(h, israel=True, include_working_days=True)
    is_yom_tov = yom_tov_name in YOM_TOV_NAMES
    is_chol_hamoed = (not is_yom_tov) and any_name in CHOL_HAMOED_FESTIVALS
    return DayInfo(
        day=d,
        hebrew_date=h.hebrew_date_string(),
        holiday=hebrewcal.holiday(h, israel=True, hebrew=True),
        is_shabbat=d.weekday() == 5,
        is_yom_tov=is_yom_tov,
        is_chol_hamoed=is_chol_hamoed,
    )


def hebrew_to_gregorian(year: int, month: int, day: int) -> date:
    """month לפי pyluach: 1=ניסן ... 7=תשרי ... 12=אדר (13=אדר ב' בשנה מעוברת)."""
    return pl_dates.HebrewDate(year, month, day).to_pydate()


def gregorian_to_hebrew(d: date) -> tuple[int, int, int]:
    h = pl_dates.GregorianDate.from_pydate(d).to_heb()
    return h.year, h.month, h.day


class JewishCalendar:
    """מימוש RestTimeProvider לעיר מסוימת."""

    def __init__(self, city: CityInfo, tz_name: str, buffer_minutes: int = 180, block_chol_hamoed: bool = True):
        self.city = city
        self.tz_name = tz_name
        self.buffer = timedelta(minutes=buffer_minutes)
        self.block_chol_hamoed = block_chol_hamoed

    def candle_lighting(self, d: date) -> datetime:
        return zmanim.sunset(d, self.city, self.tz_name) - timedelta(minutes=self.city.candle_offset_minutes)

    def nightfall(self, d: date) -> datetime:
        return zmanim.nightfall(d, self.city, self.tz_name)

    def blocked_intervals(self, first: date, last: date) -> list[Interval]:
        blocks: list[Interval] = []
        d = first - timedelta(days=1)
        end = last + timedelta(days=1)
        while d <= end:
            info = day_info(d)
            if info.is_rest_day and not day_info(d - timedelta(days=1)).is_rest_day:
                run_end = d
                while day_info(run_end + timedelta(days=1)).is_rest_day:
                    run_end += timedelta(days=1)
                start = self.candle_lighting(d - timedelta(days=1)) - self.buffer
                blocks.append(Interval(start, self.nightfall(run_end)))
                d = run_end + timedelta(days=1)
                continue
            if self.block_chol_hamoed and info.is_chol_hamoed:
                blocks.append(Interval(self.nightfall(d - timedelta(days=1)), self.nightfall(d)))
            d += timedelta(days=1)
        return normalize(blocks)

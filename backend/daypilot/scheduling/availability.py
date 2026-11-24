"""
חישוב זמן פנוי.

פנוי = שעות פעילות + זמן פנוי נוסף
       פחות לימודים, עבודה, התחייבויות, חסימות, שבתות וחגים, ומה שכבר עבר.

ימי השבוע ממוספרים מיום ראשון: 0=ראשון ... 6=שבת.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from daypilot.domain.enums import AvailabilityKind, ExceptionKind
from daypilot.domain.intervals import Interval, intersect, normalize, subtract
from daypilot.utils.clock import local_datetime

DEFAULT_ACTIVE_START = time(8, 0)
DEFAULT_ACTIVE_END = time(22, 0)


def il_weekday(d: date) -> int:
    """0=ראשון ... 6=שבת (Python: 0=שני)."""
    return (d.weekday() + 1) % 7


@dataclass(frozen=True)
class WeeklyRule:
    weekday: int  # 0=ראשון
    start: time
    end: time
    kind: AvailabilityKind
    label: str = ""


@dataclass(frozen=True)
class DateException:
    day: date
    kind: ExceptionKind
    start: time | None = None  # None = כל היום
    end: time | None = None
    label: str = ""


@dataclass
class Availability:
    active: list[Interval] = field(default_factory=list)
    busy: list[Interval] = field(default_factory=list)
    free: list[Interval] = field(default_factory=list)
    preferred: list[Interval] = field(default_factory=list)


def _window(d: date, start: time, end: time, tz_name: str) -> Interval:
    begin = local_datetime(d, start, tz_name)
    finish_day = d if end > start else d + timedelta(days=1)  # חוצה חצות
    return Interval(begin, local_datetime(finish_day, end, tz_name))


def _whole_day(d: date, tz_name: str) -> Interval:
    return Interval(local_datetime(d, time(0), tz_name), local_datetime(d + timedelta(days=1), time(0), tz_name))


def compute_availability(
    first_day: date,
    last_day: date,
    rules: list[WeeklyRule],
    exceptions: list[DateException],
    blocked: list[Interval],
    now: datetime,
    tz_name: str,
) -> Availability:
    has_active_rules = any(r.kind == AvailabilityKind.ACTIVE_HOURS for r in rules)
    active: list[Interval] = []
    busy: list[Interval] = list(blocked)
    preferred: list[Interval] = []

    day = first_day
    while day <= last_day:
        wd = il_weekday(day)
        todays = [r for r in rules if r.weekday == wd]
        if has_active_rules:
            active += [_window(day, r.start, r.end, tz_name) for r in todays if r.kind == AvailabilityKind.ACTIVE_HOURS]
        else:
            active.append(_window(day, DEFAULT_ACTIVE_START, DEFAULT_ACTIVE_END, tz_name))
        busy += [_window(day, r.start, r.end, tz_name) for r in todays if r.kind.is_busy]
        preferred += [
            _window(day, r.start, r.end, tz_name) for r in todays if r.kind == AvailabilityKind.PREFERRED_STUDY
        ]
        day += timedelta(days=1)

    for ex in exceptions:
        if not (first_day <= ex.day <= last_day):
            continue
        window = (
            _whole_day(ex.day, tz_name)
            if ex.start is None or ex.end is None
            else _window(ex.day, ex.start, ex.end, tz_name)
        )
        if ex.kind == ExceptionKind.BLOCKED:
            busy.append(window)
        else:
            active.append(window)

    horizon = Interval(
        max(now, local_datetime(first_day, time(0), tz_name)),
        local_datetime(last_day + timedelta(days=1), time(0), tz_name),
    )
    active = intersect(normalize(active), [horizon])
    busy = normalize(busy)
    free = subtract(active, busy)
    preferred = intersect(subtract(preferred, busy), free)
    return Availability(active=active, busy=busy, free=free, preferred=preferred)

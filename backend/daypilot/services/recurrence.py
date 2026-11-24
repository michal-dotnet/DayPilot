"""
פריסת משימות חוזרות למופעים.

משימה חוזרת מוגדרת ב-RRULE (למשל FREQ=WEEKLY;BYDAY=WE).
כל מופע יכול לכלול:
- אירוע קבוע (שעה + משך) שחוסם זמן ביומן, למשל בוחן.
- זמן הכנה שמשובץ לפני המופע, כמו משימה מתוזמנת קטנה.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from dateutil.rrule import rrulestr

from daypilot.domain.intervals import Interval
from daypilot.utils.clock import local_datetime


@dataclass(frozen=True)
class Occurrence:
    task_id: int
    day: date
    event: Interval | None  # הזמן שהאירוע עצמו תופס
    deadline: datetime  # עד מתי צריך לסיים הכנה (תחילת האירוע, או סוף היום)


def expand_occurrences(
    task_id: int,
    rule: str,
    series_start: date,
    series_end: date | None,
    first: date,
    last: date,
    occurrence_time: time | None,
    occurrence_minutes: int | None,
    tz_name: str,
) -> list[Occurrence]:
    dtstart = datetime.combine(series_start, time(0))
    parsed = rrulestr(rule, dtstart=dtstart)
    window_end = min(last, series_end) if series_end else last
    days = [
        dt.date()
        for dt in parsed.between(datetime.combine(first, time(0)), datetime.combine(window_end, time(23, 59)), inc=True)
    ]
    result: list[Occurrence] = []
    for d in days:
        if occurrence_time is not None and occurrence_minutes:
            start = local_datetime(d, occurrence_time, tz_name)
            event = Interval(start, start + timedelta(minutes=occurrence_minutes))
            deadline = start
        else:
            event = None
            deadline = local_datetime(d + timedelta(days=1), time(0), tz_name)
        result.append(Occurrence(task_id, d, event, deadline))
    return result

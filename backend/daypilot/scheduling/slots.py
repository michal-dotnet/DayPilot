"""
חלוקת זמן פנוי למשבצות קבועות.

משבצות מיושרות לשעון המקומי (למשל :00 ו-:30), כך שמפגש לא מתחיל ב-17:07.
משבצת שלא נכנסת במלואה לחלון פנוי לא נוצרת.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from daypilot.domain.intervals import Interval, normalize
from daypilot.utils.clock import get_tz


@dataclass(frozen=True)
class Slot:
    index: int
    start: datetime  # aware UTC
    end: datetime
    day_key: str  # תאריך מקומי YYYY-MM-DD
    day_index: int  # ימים מאז היום הראשון באופק
    preferred: bool
    contiguous_with_prev: bool  # המשבצת הקודמת נגמרת בדיוק כשזו מתחילה


def _align_up(dt_local: datetime, slot_minutes: int) -> datetime:
    minute_of_day = dt_local.hour * 60 + dt_local.minute
    remainder = minute_of_day % slot_minutes
    base = dt_local.replace(second=0, microsecond=0)
    if remainder == 0 and dt_local.second == 0 and dt_local.microsecond == 0:
        return base
    return base + timedelta(minutes=slot_minutes - remainder)


def build_slots(
    free: list[Interval],
    preferred: list[Interval],
    slot_minutes: int,
    tz_name: str,
    first_day_local: datetime | None = None,
) -> list[Slot]:
    tz = get_tz(tz_name)
    step = timedelta(minutes=slot_minutes)
    preferred_norm = normalize(preferred)
    slots: list[Slot] = []
    first_date = None
    if first_day_local is not None:
        first_date = first_day_local.astimezone(tz).date()

    for window in normalize(free):
        local_start = _align_up(window.start.astimezone(tz), slot_minutes)
        cursor = local_start
        while True:
            # חישוב בשעון "קיר" ואז המרה; zoneinfo מטפל במעברי שעון
            slot_start = cursor.astimezone(tz)
            slot_end = (slot_start.astimezone(timezone.utc) + step).astimezone(tz)
            if slot_end > window.end:
                break
            day = slot_start.date()
            if first_date is None:
                first_date = day
            prev = slots[-1] if slots else None
            interval = Interval(slot_start, slot_end)
            slots.append(
                Slot(
                    index=len(slots),
                    start=slot_start.astimezone(timezone.utc),
                    end=slot_end.astimezone(timezone.utc),
                    day_key=day.isoformat(),
                    day_index=(day - first_date).days,
                    preferred=any(p.contains(interval) for p in preferred_norm),
                    contiguous_with_prev=bool(prev and prev.end == slot_start),
                )
            )
            cursor = slot_end
    return slots

"""
עזרי תאריכים לאגנט.

המודל מבין את הביטוי ("ביום שלישי הבא"), והקוד מחשב את התאריך:
- טבלת ימים קרובים שנכנסת להקשר בכל תור (תאריך, יום בשבוע, תאריך עברי, חג).
- המרה של מחרוזות מהמודל לזמן aware, עם ולידציה.
- המרה של תאריך עברי (יום + שם חודש) לתאריך לועזי.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from daypilot.jewish_calendar.calendar import day_info, gregorian_to_hebrew, hebrew_to_gregorian
from daypilot.utils.clock import get_tz

HEBREW_WEEKDAYS = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"]  # 0=ראשון

# שמות חודשים -> מספר חודש לפי pyluach (1=ניסן ... 7=תשרי ... 12=אדר, 13=אדר ב')
HEBREW_MONTHS = {
    "ניסן": 1, "אייר": 2, "סיון": 3, "סיוון": 3, "תמוז": 4, "אב": 5, "מנחם אב": 5, "אלול": 6,
    "תשרי": 7, "חשון": 8, "חשוון": 8, "מרחשון": 8, "מרחשוון": 8, "כסלו": 9, "כסליו": 9, "טבת": 10,
    "שבט": 11, "אדר": 12, "אדר א": 12, "אדר א'": 12, "אדר ב": 13, "אדר ב'": 13,
}


def il_weekday(d: date) -> int:
    return (d.weekday() + 1) % 7


def days_table(today: date, days: int = 14) -> str:
    """טבלה קצרה שהמודל משתמש בה כדי לתרגם ביטויים יחסיים לתאריך מדויק."""
    lines = ["date | weekday | hebrew date | holiday"]
    for i in range(days):
        d = today + timedelta(days=i)
        info = day_info(d)
        mark = " (today)" if i == 0 else (" (tomorrow)" if i == 1 else "")
        holiday = info.holiday or ""
        lines.append(f"{d.isoformat()}{mark} | {HEBREW_WEEKDAYS[il_weekday(d)]} | {info.hebrew_date} | {holiday}")
    return "\n".join(lines)


class DateParseError(ValueError):
    pass


def parse_local_datetime(value: str, tz_name: str, date_only_time: time = time(0)) -> tuple[datetime, bool]:
    """
    מחזיר (datetime aware, האם ניתן רק תאריך).
    קלט: '2026-12-03T09:00', '2026-12-03 09:00', '2026-12-03T09:00+02:00' או '2026-12-03'.
    בלי אזור זמן: מפורש כשעון ישראל.
    """
    text = (value or "").strip().replace(" ", "T", 1)
    if not text:
        raise DateParseError("empty date")
    try:
        if len(text) == 10:
            d = date.fromisoformat(text)
            return datetime.combine(d, date_only_time, tzinfo=get_tz(tz_name)), True
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise DateParseError(f"cannot parse date '{value}', use ISO format YYYY-MM-DD or YYYY-MM-DDTHH:MM") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=get_tz(tz_name))
    return dt, False


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError as exc:
        raise DateParseError(f"cannot parse date '{value}', use YYYY-MM-DD") from exc


def resolve_hebrew(day: int, month_name: str, today: date, year: int | None = None) -> date:
    """תאריך עברי -> לועזי. בלי שנה: המופע הקרוב שלא עבר."""
    name = month_name.strip().replace("״", "").replace('"', "")
    month = HEBREW_MONTHS.get(name)
    if month is None:
        raise DateParseError(f"unknown Hebrew month '{month_name}'")
    if not 1 <= day <= 30:
        raise DateParseError("day must be between 1 and 30")
    if year is not None:
        return hebrew_to_gregorian(year, month, day)
    current_year = gregorian_to_hebrew(today)[0]
    for y in (current_year, current_year + 1):
        try:
            candidate = hebrew_to_gregorian(y, month, day)
        except ValueError:
            continue
        if candidate >= today:
            return candidate
    raise DateParseError("could not resolve the Hebrew date")

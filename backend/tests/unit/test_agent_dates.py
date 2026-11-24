"""בדיקות לעזרי התאריכים של האגנט."""

from datetime import date, time

import pytest

from daypilot.agent.dates import DateParseError, days_table, parse_local_datetime, resolve_hebrew
from daypilot.jewish_calendar.calendar import gregorian_to_hebrew

TZ = "Asia/Jerusalem"


def test_parse_naive_is_israel_time():
    dt, date_only = parse_local_datetime("2026-12-03T09:30", TZ)
    assert not date_only
    assert dt.utcoffset().total_seconds() == 2 * 3600
    assert dt.time() == time(9, 30)


def test_parse_date_only_is_start_of_day():
    dt, date_only = parse_local_datetime("2026-12-03", TZ)
    assert date_only and dt.time() == time(0)


def test_parse_rejects_garbage():
    with pytest.raises(DateParseError):
        parse_local_datetime("next tuesday", TZ)


def test_resolve_hebrew_next_occurrence():
    today = date(2026, 11, 29)
    result = resolve_hebrew(15, "שבט", today=today)
    assert result > today
    assert gregorian_to_hebrew(result) == (5787, 11, 15)  # ט"ו בשבט תשפ"ז


def test_resolve_hebrew_unknown_month():
    with pytest.raises(DateParseError):
        resolve_hebrew(1, "ינואר", today=date(2026, 11, 29))


def test_days_table_has_weekdays_and_hebrew_dates():
    table = days_table(date(2026, 11, 29), days=3)
    assert "2026-11-29 (today) | ראשון" in table
    assert "2026-11-30 (tomorrow) | שני" in table

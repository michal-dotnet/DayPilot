"""בדיקות לקטעי זמן, משבצות וחישוב זמן פנוי."""

from datetime import date, datetime, time, timedelta, timezone

from daypilot.domain.enums import AvailabilityKind, ExceptionKind
from daypilot.domain.intervals import Interval, intersect, normalize, subtract, total_minutes
from daypilot.scheduling.availability import DateException, WeeklyRule, compute_availability, il_weekday
from daypilot.scheduling.slots import build_slots
from daypilot.utils.clock import local_datetime

TZ = "Asia/Jerusalem"


def L(d: date, h: int, m: int = 0) -> datetime:
    return local_datetime(d, time(h, m), TZ)


SUNDAY = date(2026, 11, 29)  # יום ראשון


def test_il_weekday_starts_on_sunday():
    assert il_weekday(SUNDAY) == 0
    assert il_weekday(SUNDAY + timedelta(days=6)) == 6  # שבת


def test_normalize_merges_touching_and_overlapping():
    a = Interval(L(SUNDAY, 8), L(SUNDAY, 10))
    b = Interval(L(SUNDAY, 10), L(SUNDAY, 11))
    c = Interval(L(SUNDAY, 10, 30), L(SUNDAY, 12))
    assert normalize([c, a, b]) == [Interval(L(SUNDAY, 8), L(SUNDAY, 12))]


def test_subtract_splits_interval():
    base = [Interval(L(SUNDAY, 8), L(SUNDAY, 18))]
    cut = [Interval(L(SUNDAY, 10), L(SUNDAY, 12)), Interval(L(SUNDAY, 17), L(SUNDAY, 19))]
    assert subtract(base, cut) == [
        Interval(L(SUNDAY, 8), L(SUNDAY, 10)),
        Interval(L(SUNDAY, 12), L(SUNDAY, 17)),
    ]


def test_intersect_and_total():
    a = [Interval(L(SUNDAY, 8), L(SUNDAY, 12))]
    b = [Interval(L(SUNDAY, 11), L(SUNDAY, 14))]
    assert intersect(a, b) == [Interval(L(SUNDAY, 11), L(SUNDAY, 12))]
    assert total_minutes(a + b) == 6 * 60


def test_availability_subtracts_classes_blocks_and_past():
    rules = [
        WeeklyRule(0, time(8), time(20), AvailabilityKind.ACTIVE_HOURS),
        WeeklyRule(0, time(9), time(13), AvailabilityKind.CLASS),
        WeeklyRule(0, time(17), time(19), AvailabilityKind.PREFERRED_STUDY),
    ]
    now = L(SUNDAY, 8, 15)
    blocked = [Interval(L(SUNDAY, 15), L(SUNDAY, 16))]
    av = compute_availability(SUNDAY, SUNDAY, rules, [], blocked, now, TZ)
    assert av.free == [
        Interval(now, L(SUNDAY, 9)),
        Interval(L(SUNDAY, 13), L(SUNDAY, 15)),
        Interval(L(SUNDAY, 16), L(SUNDAY, 20)),
    ]
    assert av.preferred == [Interval(L(SUNDAY, 17), L(SUNDAY, 19))]


def test_day_without_active_rule_is_unavailable_when_rules_exist():
    rules = [WeeklyRule(0, time(8), time(20), AvailabilityKind.ACTIVE_HOURS)]
    monday = SUNDAY + timedelta(days=1)
    av = compute_availability(monday, monday, rules, [], [], L(SUNDAY, 0), TZ)
    assert av.free == []


def test_default_active_hours_when_no_rules():
    av = compute_availability(SUNDAY, SUNDAY, [], [], [], L(SUNDAY, 0), TZ)
    assert av.free == [Interval(L(SUNDAY, 8), L(SUNDAY, 22))]


def test_exceptions_block_whole_day_and_add_time():
    monday = SUNDAY + timedelta(days=1)
    exceptions = [
        DateException(SUNDAY, ExceptionKind.BLOCKED),
        DateException(monday, ExceptionKind.EXTRA_AVAILABLE, time(22), time(23)),
    ]
    av = compute_availability(SUNDAY, monday, [], exceptions, [], L(SUNDAY, 0), TZ)
    assert av.free == [Interval(L(monday, 8), L(monday, 23))]
    assert total_minutes(av.free) == 15 * 60


def test_slots_are_aligned_and_marked():
    free = [Interval(L(SUNDAY, 8, 10), L(SUNDAY, 10))]
    preferred = [Interval(L(SUNDAY, 9), L(SUNDAY, 10))]
    slots = build_slots(free, preferred, 30, TZ)
    assert [s.start for s in slots] == [
        L(SUNDAY, 8, 30).astimezone(timezone.utc),
        L(SUNDAY, 9).astimezone(timezone.utc),
        L(SUNDAY, 9, 30).astimezone(timezone.utc),
    ]
    assert [s.preferred for s in slots] == [False, True, True]
    assert [s.contiguous_with_prev for s in slots] == [False, True, True]


def test_slots_across_dst_change_keep_30_minutes():
    # 2026-03-27 (שישי) ישראל עוברת לשעון קיץ ב-02:00
    d = date(2026, 3, 27)
    free = [Interval(L(d, 0), L(d, 4))]
    slots = build_slots(free, [], 30, TZ)
    assert all((s.end - s.start) == timedelta(minutes=30) for s in slots)
    # שעה אחת "נעלמה": 4 שעות שעון קיר הן 3 שעות אמיתיות = 6 משבצות
    assert len(slots) == 6

"""בדיקות למנוע התכנון (CP-SAT) בלי מסד נתונים."""

from datetime import timedelta

from daypilot.domain.intervals import Interval
from daypilot.scheduling.engine import CpSatScheduler
from daypilot.scheduling.types import ExistingSession, PlanningInput, SchedulableTask, SessionRules
from daypilot.utils.clock import to_local
from tests.conftest import START_DAY, TZ, L


def days(n: int, start_h: int = 8, end_h: int = 22):
    return [Interval(L(START_DAY + timedelta(days=i), start_h), L(START_DAY + timedelta(days=i), end_h)) for i in range(n)]


def plan(tasks, free, preferred=None, rules=None, previous=None):
    data = PlanningInput(
        now=L(START_DAY, 8),
        free=free,
        preferred=preferred or [],
        tasks=tasks,
        rules=rules or SessionRules(),
        previous_sessions=previous or [],
        tz_name=TZ,
        time_limit_s=5,
    )
    return CpSatScheduler().plan(data)


def test_simple_task_is_fully_scheduled_in_valid_sessions():
    deadline = L(START_DAY + timedelta(days=3), 9)
    result = plan([SchedulableTask(1, "exam", 240, deadline)], days(3))
    assert result.is_complete
    assert sum(s.minutes for s in result.sessions) == 240
    for s in result.sessions:
        assert 60 <= s.minutes <= 120
        assert s.end <= deadline
        assert any(f.start <= s.start and s.end <= f.end for f in days(3))


def test_not_enough_time_reports_exact_shortfall():
    deadline = L(START_DAY + timedelta(days=1), 0)  # רק היום
    result = plan([SchedulableTask(1, "big", 20 * 60, deadline)], days(1), rules=SessionRules(daily_max_minutes=360))
    assert not result.is_complete
    assert result.shortfalls[0].scheduled_minutes == 360
    assert result.shortfalls[0].missing_minutes == 14 * 60


def test_daily_max_is_respected():
    deadline = L(START_DAY + timedelta(days=4), 0)
    result = plan([SchedulableTask(1, "a", 10 * 60, deadline)], days(4), rules=SessionRules(daily_max_minutes=180))
    per_day = {}
    for s in result.sessions:
        d = to_local(s.start, TZ).date()
        per_day[d] = per_day.get(d, 0) + s.minutes
    assert max(per_day.values()) <= 180


def test_two_tasks_never_overlap():
    deadline = L(START_DAY + timedelta(days=2), 0)
    result = plan(
        [SchedulableTask(1, "a", 300, deadline), SchedulableTask(2, "b", 300, deadline)],
        days(2),
    )
    assert result.is_complete
    ordered = sorted(result.sessions, key=lambda s: s.start)
    for a, b in zip(ordered, ordered[1:]):
        assert a.end <= b.start


def test_preferred_windows_are_used_when_possible():
    deadline = L(START_DAY + timedelta(days=1), 0)
    preferred = [Interval(L(START_DAY, 18), L(START_DAY, 20))]
    result = plan([SchedulableTask(1, "a", 120, deadline)], days(1), preferred=preferred)
    assert result.sessions == [result.sessions[0]]
    assert result.sessions[0].start == L(START_DAY, 18)


def test_replanning_keeps_previous_sessions():
    deadline = L(START_DAY + timedelta(days=3), 0)
    previous = [ExistingSession(1, L(START_DAY + timedelta(days=1), 14), L(START_DAY + timedelta(days=1), 16))]
    result = plan([SchedulableTask(1, "a", 120, deadline)], days(3), previous=previous)
    assert result.moved_minutes == 0
    assert (result.sessions[0].start, result.sessions[0].end) == (previous[0].start, previous[0].end)


def test_allowed_windows_restrict_task():
    tuesday = START_DAY + timedelta(days=2)
    window = [Interval(L(tuesday, 0), L(tuesday + timedelta(days=1), 0))]
    deadline = L(START_DAY + timedelta(days=4), 0)
    result = plan([SchedulableTask(1, "a", 240, deadline, allowed=window)], days(4))
    assert result.is_complete
    assert all(to_local(s.start, TZ).date() == tuesday for s in result.sessions)


def test_short_remaining_allows_short_session():
    deadline = L(START_DAY + timedelta(days=1), 0)
    result = plan([SchedulableTask(1, "a", 30, deadline)], days(1))
    assert result.is_complete
    assert result.sessions[0].minutes == 30


def _minutes_per_day(result):
    per_day = {}
    for s in result.sessions:
        d = to_local(s.start, TZ).date()
        per_day[d] = per_day.get(d, 0) + s.minutes
    return per_day


def test_assignment_goes_to_the_earliest_day_that_fits_it_whole():
    # ש"ב של 5 שעות. ביום הראשון רק 3 שעות פנויות, בשני ובשלישי 8: הכל ביום השני
    d0, d1, d2 = (START_DAY + timedelta(days=i) for i in range(3))
    free = [Interval(L(d0, 18), L(d0, 21)), Interval(L(d1, 12), L(d1, 20)), Interval(L(d2, 12), L(d2, 20))]
    deadline = L(START_DAY + timedelta(days=3), 0)
    result = plan([SchedulableTask(1, "hw", 300, deadline)], free)
    assert result.is_complete
    assert _minutes_per_day(result) == {d1: 300}


def test_large_assignment_uses_as_few_days_as_possible():
    # 8 שעות, תקרה יומית 6: יומיים ולא יותר
    deadline = L(START_DAY + timedelta(days=5), 0)
    result = plan([SchedulableTask(1, "project", 8 * 60, deadline)], days(5))
    assert result.is_complete
    assert len(_minutes_per_day(result)) == 2


def test_exam_study_ramps_up_to_a_full_day_before_the_exam():
    # 10 שעות, 7 ימים: מתחילים בקטן, והיום שלפני המבחן מלא (תקרה 6 שעות)
    deadline = L(START_DAY + timedelta(days=7), 0)
    result = plan([SchedulableTask(1, "exam", 10 * 60, deadline, style="exam")], days(7))
    assert result.is_complete
    per_day = _minutes_per_day(result)
    ordered = [per_day[d] for d in sorted(per_day)]
    assert per_day[START_DAY + timedelta(days=6)] == 360
    assert ordered == sorted(ordered)  # עולה בהדרגה
    assert ordered[0] < 360
    assert START_DAY not in per_day  # לא מתחילים מוקדם מדי


def test_big_exam_gets_two_full_days():
    deadline = L(START_DAY + timedelta(days=7), 0)
    result = plan([SchedulableTask(1, "exam", 20 * 60, deadline, style="exam")], days(7))
    assert result.is_complete
    per_day = _minutes_per_day(result)
    assert per_day[START_DAY + timedelta(days=6)] == 360
    assert per_day[START_DAY + timedelta(days=5)] == 360


def test_exam_ramp_targets_profile():
    from daypilot.scheduling.engine import exam_ramp_targets

    days_ = [f"d{i}" for i in range(7)]
    cap = {d: 12 for d in days_}
    assert list(exam_ramp_targets(days_, cap, 20, 12).values()) == [0, 0, 0, 0, 3, 5, 12]
    assert list(exam_ramp_targets(days_, cap, 4, 12).values()) == [0, 0, 0, 0, 0, 0, 4]
    blocked = dict(cap, d6=0)  # היום שלפני המבחן חסום (למשל שבת): היום המלא עובר ליום שלפניו
    assert exam_ramp_targets(days_, blocked, 20, 12)["d5"] == 12

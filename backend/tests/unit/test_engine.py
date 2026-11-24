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

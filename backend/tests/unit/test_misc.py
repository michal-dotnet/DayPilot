"""בדיקות יחידה קטנות: התנגשויות, הסתרת סודות, ולידציה של סכמות."""

from datetime import timedelta

import pytest
from pydantic import ValidationError

from daypilot.domain.enums import ConflictKind, TaskType
from daypilot.domain.intervals import Interval
from daypilot.domain.schemas import DateExceptionIn, TaskCreate
from daypilot.scheduling.conflicts import capacity_conflicts, find_overlaps, overload_conflicts
from daypilot.scheduling.types import ExistingSession, Shortfall
from daypilot.utils.logging import redact
from tests.conftest import START_DAY, TZ, L


def test_overlap_with_busy_and_between_sessions():
    a = ExistingSession(1, L(START_DAY, 10), L(START_DAY, 12), session_id=1)
    b = ExistingSession(2, L(START_DAY, 11), L(START_DAY, 13), session_id=2)
    busy = [Interval(L(START_DAY, 9), L(START_DAY, 10, 30))]
    found = find_overlaps([a, b], busy)
    kinds = [c.kind for c in found]
    assert kinds.count(ConflictKind.OVERLAP) == 2
    assert any(set(c.task_ids) == {1, 2} for c in found)


def test_capacity_and_overload():
    assert capacity_conflicts([Shortfall(1, 600, 600)]) == []
    [c] = capacity_conflicts([Shortfall(1, 600, 360)])
    assert c.details["missing_minutes"] == 240
    heavy = [ExistingSession(1, L(START_DAY, 8), L(START_DAY, 14))]
    [o] = overload_conflicts(heavy, daily_max_minutes=360, tz_name=TZ)
    assert o.details["day"] == START_DAY.isoformat()
    light = [ExistingSession(1, L(START_DAY, 8), L(START_DAY, 9))]
    assert overload_conflicts(light, daily_max_minutes=360, tz_name=TZ) == []


def test_secrets_are_redacted():
    text = "key=sk-abcdefghijklmnop and lsv2_pt_1234567890abcdef OPENAI_API_KEY: hunter2"
    clean = redact(text)
    assert "sk-abcdefghijklmnop" not in clean
    assert "lsv2_pt_1234567890abcdef" not in clean
    assert "hunter2" not in clean


def test_recurring_task_needs_rule_and_event_or_prep():
    with pytest.raises(ValidationError):
        TaskCreate(title="בוחן", task_type=TaskType.RECURRING)
    with pytest.raises(ValidationError):
        TaskCreate(title="בוחן", task_type=TaskType.RECURRING, recurrence_rule="FREQ=WEEKLY;BYDAY=WE")
    ok = TaskCreate(title="בוחן", task_type=TaskType.RECURRING, recurrence_rule="FREQ=WEEKLY;BYDAY=WE", prep_minutes=60)
    assert ok.prep_minutes == 60


def test_deadline_must_have_timezone():
    from datetime import datetime

    with pytest.raises(ValidationError):
        TaskCreate(title="x", task_type=TaskType.SCHEDULED, deadline=datetime(2026, 12, 1, 9), estimated_minutes=60)


def test_exception_times_both_or_none():
    from datetime import time

    with pytest.raises(ValidationError):
        DateExceptionIn(day=START_DAY + timedelta(days=1), kind="blocked", start_time=time(9))

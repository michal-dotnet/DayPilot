"""
fixtures משותפים.

- מסד SQLite בזיכרון לכל בדיקה.
- שעון קבוע: יום ראשון 29.11.2026, 08:00 שעון ישראל.
- ספק זמני מנוחה מזויף, כדי שבדיקות התכנון לא יהיו תלויות בספריית hdate.
"""

from __future__ import annotations

import os
from datetime import date, datetime, time

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-key")

from daypilot.db.session import create_schema, make_engine, make_session_factory  # noqa: E402
from daypilot.domain.intervals import Interval  # noqa: E402
from daypilot.scheduling.engine import CpSatScheduler  # noqa: E402
from daypilot.services.schedule_service import ScheduleService  # noqa: E402
from daypilot.services.settings_service import SettingsService  # noqa: E402
from daypilot.services.task_service import TaskService  # noqa: E402
from daypilot.utils.clock import FixedClock, local_datetime  # noqa: E402

TZ = "Asia/Jerusalem"
START_DAY = date(2026, 11, 29)  # יום ראשון


def L(d: date, h: int, m: int = 0) -> datetime:
    return local_datetime(d, time(h, m), TZ)


class FakeRestProvider:
    def __init__(self, blocks: list[Interval] | None = None):
        self.blocks = blocks or []

    def blocked_intervals(self, first, last):
        return [b for b in self.blocks]


@pytest.fixture
def clock():
    return FixedClock(L(START_DAY, 8))


@pytest.fixture
def db():
    engine = make_engine("sqlite:///:memory:")
    create_schema(engine)
    factory = make_session_factory(engine)
    session = factory()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def rest():
    return FakeRestProvider()


@pytest.fixture
def user(db, clock):
    u = SettingsService(db, clock).ensure_default_user("test")
    db.commit()
    return u


@pytest.fixture
def tasks(db, clock):
    return TaskService(db, clock)


@pytest.fixture
def schedule(db, clock, rest):
    return ScheduleService(db, clock, CpSatScheduler(), lambda _user: rest, slot_minutes=30, time_limit_s=5.0)

"""
הרכבת התלויות במקום אחד.

ה-API, ה-CLI, האגנט ותהליך התזכורות יוצרים Services דרך AppContainer,
כך שכולם משתמשים באותו מסד, באותו שעון ובאותו מנוע תכנון.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy.orm import Session

from daypilot.config import Settings, get_settings
from daypilot.db.models import User
from daypilot.db.session import make_engine, make_session_factory, migrate, unit_of_work
from daypilot.jewish_calendar.calendar import JewishCalendar
from daypilot.jewish_calendar.cities import DEFAULT_CITY_KEY, CityInfo, city_by_key
from daypilot.scheduling.engine import CpSatScheduler, Scheduler
from daypilot.services.conversation_service import ConversationService
from daypilot.services.schedule_service import RestTimeProvider, ScheduleService
from daypilot.services.settings_service import SettingsService
from daypilot.services.task_service import TaskService
from daypilot.utils.clock import Clock, SystemClock
from daypilot.utils.tls import use_system_certificates


@dataclass
class Services:
    session: Session
    tasks: TaskService
    schedule: ScheduleService
    settings: SettingsService
    conversations: ConversationService


class AppContainer:
    def __init__(self, settings: Settings | None = None, clock: Clock | None = None, scheduler: Scheduler | None = None):
        self.settings = settings or get_settings()
        use_system_certificates(self.settings.use_system_certificates)
        self.settings.export_tracing_env()
        self.clock = clock or SystemClock()
        self.scheduler = scheduler or CpSatScheduler()
        self.settings.ensure_dirs()
        self.engine = make_engine(self.settings.app_database_url)
        migrate(self.engine)
        self.session_factory = make_session_factory(self.engine)

    def rest_provider_for(self, user: User) -> RestTimeProvider:
        prefs = user.preferences
        if user.city is not None:
            c = user.city
            city = CityInfo(c.key, c.name_he, c.name_en, c.latitude, c.longitude, c.altitude, c.candle_offset_minutes)
        else:
            city = city_by_key(DEFAULT_CITY_KEY)
        return JewishCalendar(
            city,
            user.timezone,
            buffer_minutes=prefs.shabbat_buffer_minutes if prefs else 180,
            block_chol_hamoed=prefs.block_chol_hamoed if prefs else True,
        )

    def services(self, session: Session) -> Services:
        return Services(
            session=session,
            tasks=TaskService(session, self.clock),
            schedule=ScheduleService(
                session,
                self.clock,
                self.scheduler,
                self.rest_provider_for,
                slot_minutes=self.settings.slot_minutes,
                time_limit_s=self.settings.scheduler_time_limit_s,
            ),
            settings=SettingsService(session, self.clock),
            conversations=ConversationService(session, self.clock),
        )

    @contextmanager
    def unit(self) -> Iterator[Services]:
        """טרנזקציה אחת עם כל ה-Services."""
        with unit_of_work(self.session_factory) as session:
            yield self.services(session)

    def default_user_id(self) -> int:
        with self.unit() as svc:
            return svc.settings.ensure_default_user().id

"""
הגדרות: משתמשת ברירת מחדל, ערים, העדפות, שעות קבועות וחריגים.

שינוי בהגדרות נשמר מיד (אוטומטי לפי המדיניות). אם הוא משפיע על הלוח,
האגנט מציע תכנון מחדש, שממתין לאישור כמו כל שינוי אחר בלוח.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot.db.models import AvailabilityException, AvailabilityRule, City, User, UserPreferences
from daypilot.db.repositories.users import UserRepository
from daypilot.domain.schemas import DateExceptionIn, PreferencesUpdate, WeeklyRuleIn
from daypilot.jewish_calendar.cities import CITIES, DEFAULT_CITY_KEY
from daypilot.services.errors import NotFoundError, ValidationError
from daypilot.utils.clock import Clock


class SettingsService:
    def __init__(self, session: Session, clock: Clock):
        self.s = session
        self.clock = clock
        self.users = UserRepository(session)

    def seed_cities(self) -> None:
        existing = {c.key for c in self.s.scalars(select(City))}
        for c in CITIES:
            if c.key not in existing:
                self.s.add(
                    City(
                        key=c.key, name_he=c.name_he, name_en=c.name_en, latitude=c.latitude,
                        longitude=c.longitude, altitude=c.altitude, candle_offset_minutes=c.candle_offset_minutes,
                    )
                )
        self.s.flush()

    def ensure_default_user(self, name: str = "") -> User:
        """המערכת מתחילה כמשתמשת יחידה: יוצרת אותה בפעם הראשונה."""
        self.seed_cities()
        user = self.users.first()
        if user is None:
            city = self.users.city_by_key(DEFAULT_CITY_KEY)
            user = self.users.create(name=name, now=self.clock.now(), city_id=city.id if city else None)
        return user

    def preferences(self, user_id: int) -> UserPreferences:
        return self.users.preferences(user_id)

    def update_preferences(self, user_id: int, data: PreferencesUpdate) -> UserPreferences:
        user = self.users.get(user_id)
        if user is None:
            raise NotFoundError("user not found")
        prefs = self.users.preferences(user_id)
        changes = data.model_dump(exclude_none=True)
        city_key = changes.pop("city_key", None)
        language = changes.pop("ui_language", None)
        if city_key:
            city = self.users.city_by_key(city_key)
            if city is None:
                raise ValidationError(f"unknown city '{city_key}'", known=[c.key for c in self.users.cities()])
            user.city_id = city.id
        if language:
            user.ui_language = language
        for key, value in changes.items():
            setattr(prefs, key, value)
        if prefs.min_session_minutes > prefs.max_session_minutes:
            raise ValidationError("min_session_minutes cannot exceed max_session_minutes")
        return prefs

    def add_rule(self, user_id: int, data: WeeklyRuleIn) -> AvailabilityRule:
        if data.start_time == data.end_time:
            raise ValidationError("start and end times are equal")
        return self.users.add_rule(AvailabilityRule(user_id=user_id, **data.model_dump()))

    def delete_rule(self, user_id: int, rule_id: int) -> None:
        if not self.users.delete_rule(user_id, rule_id):
            raise NotFoundError(f"rule {rule_id} not found")

    def add_exception(self, user_id: int, data: DateExceptionIn) -> AvailabilityException:
        return self.users.add_exception(AvailabilityException(user_id=user_id, **data.model_dump()))

    def delete_exception(self, user_id: int, exception_id: int) -> None:
        if not self.users.delete_exception(user_id, exception_id):
            raise NotFoundError(f"exception {exception_id} not found")

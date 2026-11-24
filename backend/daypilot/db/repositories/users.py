"""גישה למשתמשים, העדפות, כללי זמינות, חריגים וערים."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from daypilot.db.models import AvailabilityException, AvailabilityRule, City, User, UserPreferences


class UserRepository:
    def __init__(self, session: Session):
        self.s = session

    # משתמשים
    def get(self, user_id: int) -> User | None:
        return self.s.get(User, user_id)

    def first(self) -> User | None:
        return self.s.scalars(select(User).order_by(User.id).limit(1)).first()

    def create(self, name: str, now: datetime, city_id: int | None = None) -> User:
        user = User(name=name, created_at=now, city_id=city_id)
        user.preferences = UserPreferences()
        self.s.add(user)
        self.s.flush()
        return user

    def preferences(self, user_id: int) -> UserPreferences:
        prefs = self.s.get(UserPreferences, user_id)
        if prefs is None:
            prefs = UserPreferences(user_id=user_id)
            self.s.add(prefs)
            self.s.flush()
        return prefs

    # זמינות
    def rules(self, user_id: int) -> list[AvailabilityRule]:
        return list(
            self.s.scalars(
                select(AvailabilityRule)
                .where(AvailabilityRule.user_id == user_id)
                .order_by(AvailabilityRule.weekday, AvailabilityRule.start_time)
            )
        )

    def add_rule(self, rule: AvailabilityRule) -> AvailabilityRule:
        self.s.add(rule)
        self.s.flush()
        return rule

    def delete_rule(self, user_id: int, rule_id: int) -> bool:
        result = self.s.execute(
            delete(AvailabilityRule).where(AvailabilityRule.id == rule_id, AvailabilityRule.user_id == user_id)
        )
        return result.rowcount > 0

    def exceptions(self, user_id: int, first: date, last: date) -> list[AvailabilityException]:
        return list(
            self.s.scalars(
                select(AvailabilityException)
                .where(
                    AvailabilityException.user_id == user_id,
                    AvailabilityException.day >= first,
                    AvailabilityException.day <= last,
                )
                .order_by(AvailabilityException.day)
            )
        )

    def add_exception(self, ex: AvailabilityException) -> AvailabilityException:
        self.s.add(ex)
        self.s.flush()
        return ex

    def delete_exception(self, user_id: int, exception_id: int) -> bool:
        result = self.s.execute(
            delete(AvailabilityException).where(
                AvailabilityException.id == exception_id, AvailabilityException.user_id == user_id
            )
        )
        return result.rowcount > 0

    # ערים
    def cities(self) -> list[City]:
        return list(self.s.scalars(select(City).order_by(City.name_he)))

    def city_by_key(self, key: str) -> City | None:
        return self.s.scalars(select(City).where(City.key == key)).first()

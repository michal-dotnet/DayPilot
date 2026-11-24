"""
טיפוסי הקלט והפלט של מנוע התכנון.

המנוע לא מכיר את מסד הנתונים, את LangGraph או את המודל.
הוא מקבל זמן פנוי ומשימות, ומחזיר שיבוץ, חוסרים וסטטוס.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from daypilot.domain.intervals import Interval


@dataclass(frozen=True)
class SchedulableTask:
    id: int
    title: str
    remaining_minutes: int
    deadline: datetime  # aware
    importance: int = 3  # 1-5
    earliest_start: datetime | None = None
    allowed: list[Interval] | None = None  # אם מוגדר: רק בחלונות האלה (שינוי ידני של תוכנית)


@dataclass(frozen=True)
class ExistingSession:
    """מפגש שכבר בתוכנית. נעול = לא זז (עבר, בוצע, או שהמשתמשת נעלה)."""

    task_id: int
    start: datetime
    end: datetime
    locked: bool = False
    session_id: int | None = None

    @property
    def interval(self) -> Interval:
        return Interval(self.start, self.end)


@dataclass(frozen=True)
class SessionRules:
    min_session_minutes: int = 60
    max_session_minutes: int = 120
    daily_max_minutes: int = 360
    slot_minutes: int = 30


@dataclass
class PlanningInput:
    now: datetime
    free: list[Interval]  # זמן פנוי לשיבוץ (כבר בלי שבתות, התחייבויות ומפגשים נעולים)
    preferred: list[Interval]  # חלונות למידה מועדפים
    tasks: list[SchedulableTask]
    rules: SessionRules = field(default_factory=SessionRules)
    previous_sessions: list[ExistingSession] = field(default_factory=list)  # מפגשים לא נעולים, ליציבות
    locked_minutes_by_day: dict[str, int] = field(default_factory=dict)  # 'YYYY-MM-DD' -> דקות תפוסות במפגשים נעולים
    tz_name: str = "Asia/Jerusalem"
    time_limit_s: float = 5.0


@dataclass(frozen=True)
class PlannedSession:
    task_id: int
    start: datetime
    end: datetime

    @property
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


@dataclass(frozen=True)
class Shortfall:
    task_id: int
    required_minutes: int
    scheduled_minutes: int

    @property
    def missing_minutes(self) -> int:
        return max(0, self.required_minutes - self.scheduled_minutes)


@dataclass
class PlanResult:
    status: str  # optimal / feasible / no_solution
    sessions: list[PlannedSession]
    shortfalls: list[Shortfall]
    moved_minutes: int = 0  # כמה דקות של מפגשים קודמים זזו
    solve_seconds: float = 0.0

    @property
    def is_complete(self) -> bool:
        return self.status in ("optimal", "feasible") and not any(s.missing_minutes for s in self.shortfalls)

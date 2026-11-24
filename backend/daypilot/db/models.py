"""
טבלאות המסד (SQLAlchemy 2.0).

בכל טבלה של נתוני משתמש יש user_id, כדי שתמיכה בכמה משתמשים לא תדרוש שינוי מבנה.
זמנים נשמרים ב-UTC דרך UTCDateTime. שעות קבועות (שעה ביום) נשמרות כ-Time מקומי.
"""

from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import JSON, Boolean, Date, Float, ForeignKey, Integer, String, Text, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from daypilot.db.base import Base, UTCDateTime
from daypilot.domain.enums import (
    AvailabilityKind,
    ExceptionKind,
    NotificationKind,
    ProposalKind,
    ProposalStatus,
    SessionStatus,
    TaskStatus,
    TaskType,
    WorkStyle,
)


class City(Base):
    __tablename__ = "cities"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(40), unique=True)
    name_he: Mapped[str] = mapped_column(String(80))
    name_en: Mapped[str] = mapped_column(String(80))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    altitude: Mapped[int] = mapped_column(Integer, default=0)
    candle_offset_minutes: Mapped[int] = mapped_column(Integer, default=20)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), default="")
    ui_language: Mapped[str] = mapped_column(String(5), default="he")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Jerusalem")
    city_id: Mapped[int | None] = mapped_column(ForeignKey("cities.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)

    city: Mapped[City | None] = relationship()
    preferences: Mapped[UserPreferences] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    min_session_minutes: Mapped[int] = mapped_column(Integer, default=60)
    max_session_minutes: Mapped[int] = mapped_column(Integer, default=120)
    daily_max_minutes: Mapped[int] = mapped_column(Integer, default=360)
    shabbat_buffer_minutes: Mapped[int] = mapped_column(Integer, default=180)
    block_chol_hamoed: Mapped[bool] = mapped_column(Boolean, default=True)
    # תזכורות
    quiet_start: Mapped[time] = mapped_column(Time, default=time(22, 0))
    quiet_end: Mapped[time] = mapped_column(Time, default=time(8, 0))
    max_popups_per_day: Mapped[int] = mapped_column(Integer, default=5)
    deadline_reminder_days: Mapped[list] = mapped_column(JSON, default=lambda: [3, 1])
    session_reminder_minutes: Mapped[int] = mapped_column(Integer, default=15)
    open_task_idle_days: Mapped[int] = mapped_column(Integer, default=7)
    no_progress_days: Mapped[int] = mapped_column(Integer, default=4)
    postponed_threshold: Mapped[int] = mapped_column(Integer, default=3)
    overload_threshold: Mapped[float] = mapped_column(Float, default=0.9)

    user: Mapped[User] = relationship(back_populates="preferences")


class AvailabilityRule(Base):
    __tablename__ = "availability_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    weekday: Mapped[int] = mapped_column(Integer)  # 0=ראשון
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    kind: Mapped[AvailabilityKind] = mapped_column(String(20))
    label: Mapped[str] = mapped_column(String(120), default="")


class AvailabilityException(Base):
    __tablename__ = "availability_exceptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    start_time: Mapped[time | None] = mapped_column(Time)
    end_time: Mapped[time | None] = mapped_column(Time)
    kind: Mapped[ExceptionKind] = mapped_column(String(20))
    label: Mapped[str] = mapped_column(String(120), default="")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    task_type: Mapped[TaskType] = mapped_column(String(20))
    status: Mapped[TaskStatus] = mapped_column(String(20), default=TaskStatus.ACTIVE)
    importance: Mapped[int] = mapped_column(Integer, default=3)  # 1-5
    work_style: Mapped[WorkStyle] = mapped_column(String(20), default=WorkStyle.ASSIGNMENT, server_default="assignment")

    # משימה מתוזמנת
    deadline: Mapped[datetime | None] = mapped_column(UTCDateTime)
    estimated_minutes: Mapped[int | None] = mapped_column(Integer)
    remaining_minutes: Mapped[int | None] = mapped_column(Integer)

    # משימה חוזרת: RRULE (למשל FREQ=WEEKLY;BYDAY=WE) + אירוע קבוע ו/או זמן הכנה לכל מופע
    recurrence_rule: Mapped[str | None] = mapped_column(String(200))
    recurrence_start: Mapped[date | None] = mapped_column(Date)
    recurrence_end: Mapped[date | None] = mapped_column(Date)
    occurrence_time: Mapped[time | None] = mapped_column(Time)  # שעת האירוע, אם יש
    occurrence_minutes: Mapped[int | None] = mapped_column(Integer)  # משך האירוע
    prep_minutes: Mapped[int | None] = mapped_column(Integer)  # זמן עבודה לפני כל מופע

    # מעקב
    postponed_count: Mapped[int] = mapped_column(Integer, default=0)
    last_progress_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    assumptions: Mapped[list] = mapped_column(JSON, default=list)  # הנחות שהאגנט עשה, מוצגות למשתמשת
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)

    sessions: Mapped[list[ScheduledSession]] = relationship(back_populates="task", cascade="all, delete-orphan")


class PlanVersion(Base):
    __tablename__ = "plan_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    reason: Mapped[str] = mapped_column(String(300), default="")
    proposal_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class ScheduledSession(Base):
    __tablename__ = "scheduled_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    start: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    end: Mapped[datetime] = mapped_column(UTCDateTime)
    status: Mapped[SessionStatus] = mapped_column(String(20), default=SessionStatus.PLANNED)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    actual_minutes: Mapped[int | None] = mapped_column(Integer)
    occurrence_date: Mapped[date | None] = mapped_column(Date)  # למופע של משימה חוזרת
    plan_version_id: Mapped[int | None] = mapped_column(ForeignKey("plan_versions.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)

    task: Mapped[Task] = relationship(back_populates="sessions")


class ProgressLog(Base):
    __tablename__ = "progress_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("scheduled_sessions.id", ondelete="SET NULL"))
    minutes: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(Text, default="")
    logged_at: Mapped[datetime] = mapped_column(UTCDateTime)


class Proposal(Base):
    """תיעוד הצעות שנסגרו. הצעה שממתינה נמצאת ב-Checkpointer, לא כאן."""

    __tablename__ = "proposals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    thread_id: Mapped[str] = mapped_column(String(100))
    kind: Mapped[ProposalKind] = mapped_column(String(30))
    status: Mapped[ProposalStatus] = mapped_column(String(20))
    summary: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    decided_at: Mapped[datetime] = mapped_column(UTCDateTime)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)  # = thread_id
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)

    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.id"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # user / assistant
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("user_id", "dedupe_key", name="uq_notifications_user_dedupe"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[NotificationKind] = mapped_column(String(30))
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    dedupe_key: Mapped[str] = mapped_column(String(200))
    popup: Mapped[bool] = mapped_column(Boolean, default=True)  # להציג גם כהתראה קופצת
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

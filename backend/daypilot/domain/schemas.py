"""
סכמות Pydantic לקלט ולפלט.

אותן סכמות משמשות את הכלים של האגנט ואת ה-API, כך שהוולידציה זהה בשני המסלולים.
"""

from __future__ import annotations

from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from daypilot.domain.enums import AvailabilityKind, ExceptionKind, ProposalKind, TaskStatus, TaskType

MAX_MINUTES = 200 * 60  # 200 שעות למשימה


def _aware(v: datetime | None) -> datetime | None:
    if v is not None and v.tzinfo is None:
        raise ValueError("datetime must include a timezone offset")
    return v


class TaskCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    task_type: TaskType
    description: str = Field(default="", max_length=2000)
    deadline: datetime | None = None
    estimated_minutes: int | None = Field(default=None, ge=5, le=MAX_MINUTES)
    importance: int = Field(default=3, ge=1, le=5)
    recurrence_rule: str | None = Field(default=None, max_length=200)
    recurrence_start: date | None = None
    recurrence_end: date | None = None
    occurrence_time: time | None = None
    occurrence_minutes: int | None = Field(default=None, ge=5, le=24 * 60)
    prep_minutes: int | None = Field(default=None, ge=5, le=24 * 60)
    assumptions: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("deadline")
    @classmethod
    def _deadline_aware(cls, v: datetime | None) -> datetime | None:
        return _aware(v)

    @model_validator(mode="after")
    def _by_type(self) -> TaskCreate:
        if self.task_type == TaskType.SCHEDULED:
            if self.deadline is None or self.estimated_minutes is None:
                raise ValueError("scheduled task requires deadline and estimated_minutes")
        if self.task_type == TaskType.RECURRING:
            if not self.recurrence_rule:
                raise ValueError("recurring task requires recurrence_rule (RRULE)")
            if self.occurrence_time is None and self.prep_minutes is None:
                raise ValueError("recurring task requires occurrence_time or prep_minutes")
            if self.occurrence_time is not None and self.occurrence_minutes is None:
                raise ValueError("occurrence_time requires occurrence_minutes")
        return self


class TaskDetailsUpdate(BaseModel):
    """שינויים פשוטים שלא משנים את הלוח (אוטומטיים לפי המדיניות)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    importance: int | None = Field(default=None, ge=1, le=5)


class ProgressReport(BaseModel):
    task_id: int
    minutes: int = Field(ge=1, le=24 * 60)
    note: str = Field(default="", max_length=1000)
    session_id: int | None = None
    completed: bool = False


class WeeklyRuleIn(BaseModel):
    weekday: int = Field(ge=0, le=6)  # 0=ראשון
    start_time: time
    end_time: time
    kind: AvailabilityKind
    label: str = Field(default="", max_length=120)


class DateExceptionIn(BaseModel):
    day: date
    kind: ExceptionKind
    start_time: time | None = None
    end_time: time | None = None
    label: str = Field(default="", max_length=120)

    @model_validator(mode="after")
    def _both_or_none(self) -> DateExceptionIn:
        if (self.start_time is None) != (self.end_time is None):
            raise ValueError("give both start_time and end_time, or neither for a whole day")
        return self


class PreferencesUpdate(BaseModel):
    min_session_minutes: int | None = Field(default=None, ge=15, le=240)
    max_session_minutes: int | None = Field(default=None, ge=30, le=480)
    daily_max_minutes: int | None = Field(default=None, ge=30, le=16 * 60)
    shabbat_buffer_minutes: int | None = Field(default=None, ge=0, le=12 * 60)
    block_chol_hamoed: bool | None = None
    city_key: str | None = None
    ui_language: str | None = Field(default=None, pattern="^(he|en)$")


# ---------- תצוגה ----------


class SessionView(BaseModel):
    id: int | None = None
    task_id: int
    task_title: str = ""
    start: datetime
    end: datetime
    status: str = "planned"
    locked: bool = False


class TaskView(BaseModel):
    id: int
    title: str
    task_type: TaskType
    status: TaskStatus
    importance: int
    deadline: datetime | None
    estimated_minutes: int | None
    remaining_minutes: int | None
    scheduled_minutes: int = 0
    done_minutes: int = 0
    postponed_count: int = 0
    recurrence_rule: str | None = None
    assumptions: list[str] = Field(default_factory=list)


# ---------- הצעות לשינוי (Human-in-the-Loop) ----------


class SessionChange(BaseModel):
    task_id: int
    start: datetime
    end: datetime
    occurrence_date: date | None = None


class TaskChange(BaseModel):
    task_id: int
    deadline: datetime | None = None
    estimated_minutes: int | None = None
    remaining_minutes: int | None = None
    delete: bool = False


class ConflictView(BaseModel):
    kind: str
    task_ids: list[int]
    message: str
    details: dict = Field(default_factory=dict)


class Alternative(BaseModel):
    key: str  # raise_daily_max / extend_evenings / drop_task:<id>
    description: str
    resolves: bool
    missing_minutes: int


class PlanProposal(BaseModel):
    """הצעה שמוצגת לאישור. נשמרת ב-State של הגרף עד שהמשתמשת מחליטה."""

    id: str
    kind: ProposalKind
    summary: str
    task_ids: list[int] = Field(default_factory=list)
    add_sessions: list[SessionChange] = Field(default_factory=list)
    remove_session_ids: list[int] = Field(default_factory=list)
    task_changes: list[TaskChange] = Field(default_factory=list)
    conflicts: list[ConflictView] = Field(default_factory=list)
    alternatives: list[Alternative] = Field(default_factory=list)
    feasible: bool = True
    moved_minutes: int = 0
    fingerprint: str = ""
    created_at: datetime

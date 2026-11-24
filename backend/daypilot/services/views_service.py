"""
נתוני תצוגה לממשק: לוח שנה, Dashboard והתקדמות.

קריאה בלבד: השירות לא משנה נתונים. כל שינוי עובר דרך הצ'אט (סעיף 11 במסמך הדרישות).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Callable

from sqlalchemy.orm import Session

from daypilot.db.models import User
from daypilot.db.repositories.tasks import ProgressRepository, SessionRepository, TaskRepository
from daypilot.db.repositories.users import UserRepository
from daypilot.domain.enums import AvailabilityKind, ExceptionKind, SessionStatus, TaskStatus, TaskType
from daypilot.domain.intervals import Interval
from daypilot.jewish_calendar.calendar import day_info
from daypilot.services.recurrence import expand_occurrences
from daypilot.services.schedule_service import RestTimeProvider
from daypilot.services.task_service import TaskService
from daypilot.utils.clock import Clock, local_datetime, to_local

HEBREW_WEEKDAYS = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"]
RULE_LABELS = {AvailabilityKind.CLASS: "לימודים", AvailabilityKind.WORK: "עבודה", AvailabilityKind.COMMITMENT: "התחייבות"}


def _minutes(start: datetime, end: datetime) -> int:
    return int((end - start).total_seconds() // 60)


class ViewsService:
    def __init__(self, session: Session, clock: Clock, rest_provider_for: Callable[[User], RestTimeProvider]):
        self.s = session
        self.clock = clock
        self.rest_provider_for = rest_provider_for
        self.users = UserRepository(session)
        self.tasks = TaskRepository(session)
        self.sessions = SessionRepository(session)
        self.progress = ProgressRepository(session)
        self.task_service = TaskService(session, clock)

    def _user(self, user_id: int) -> User:
        user = self.users.get(user_id)
        if user is None:
            raise ValueError("user not found")
        return user

    # ---------------------------------------------------------------- לוח שנה

    def calendar(self, user_id: int, first: date, last: date) -> dict:
        user = self._user(user_id)
        tz = user.timezone
        start = local_datetime(first, time(0), tz)
        end = local_datetime(last + timedelta(days=1), time(0), tz)

        days = []
        d = first
        while d <= last:
            info = day_info(d)
            days.append({
                "date": d.isoformat(), "weekday": (d.weekday() + 1) % 7, "hebrew_date": info.hebrew_date,
                "holiday": info.holiday, "is_rest_day": info.is_rest_day, "is_chol_hamoed": info.is_chol_hamoed,
            })
            d += timedelta(days=1)

        blocks: list[dict] = []
        for iv in self.rest_provider_for(user).blocked_intervals(first, last):
            label = self._rest_label(iv, tz)
            blocks.append({"start": iv.start, "end": iv.end, "kind": "rest", "label": label})
        for r in self.users.rules(user_id):
            kind = AvailabilityKind(r.kind)
            if not kind.is_busy:
                continue
            d = first
            while d <= last:
                if (d.weekday() + 1) % 7 == r.weekday:
                    s = local_datetime(d, r.start_time, tz)
                    e = local_datetime(d if r.end_time > r.start_time else d + timedelta(days=1), r.end_time, tz)
                    blocks.append({"start": s, "end": e, "kind": kind.value, "label": r.label or RULE_LABELS.get(kind, "")})
                d += timedelta(days=1)
        for ex in self.users.exceptions(user_id, first, last):
            if ExceptionKind(ex.kind) != ExceptionKind.BLOCKED:
                continue
            s = local_datetime(ex.day, ex.start_time or time(0), tz)
            e = local_datetime(ex.day, ex.end_time, tz) if ex.end_time else local_datetime(ex.day + timedelta(days=1), time(0), tz)
            blocks.append({"start": s, "end": e, "kind": "blocked", "label": ex.label or "לא פנויה"})
        for t in self.tasks.list(user_id, types=(TaskType.RECURRING,)):
            if not (t.recurrence_rule and t.occurrence_time and t.occurrence_minutes):
                continue
            for occ in expand_occurrences(t.id, t.recurrence_rule, t.recurrence_start or first, t.recurrence_end, first, last,
                                          t.occurrence_time, t.occurrence_minutes, tz):
                blocks.append({"start": occ.event.start, "end": occ.event.end, "kind": "event", "label": t.title,
                               "task_id": t.id})

        titles = {t.id: t.title for t in self.tasks.list(user_id, statuses=None)}
        sessions = [
            {"id": r.id, "task_id": r.task_id, "task_title": titles.get(r.task_id, ""), "start": r.start, "end": r.end,
             "status": r.status, "locked": r.locked}
            for r in self.sessions.in_range(user_id, start, end)
            if r.status != SessionStatus.CANCELLED
        ]
        return {"days": days, "blocks": sorted(blocks, key=lambda b: b["start"]), "sessions": sessions}

    @staticmethod
    def _rest_label(iv: Interval, tz: str) -> str:
        d = to_local(iv.start, tz).date()
        end_day = to_local(iv.end, tz).date()
        names = []
        while d <= end_day:
            info = day_info(d)
            if info.holiday and (info.is_yom_tov or info.is_chol_hamoed) and info.holiday not in names:
                names.append(info.holiday)
            d += timedelta(days=1)
        if names:
            return " / ".join(names)
        return "שבת"

    # ---------------------------------------------------------------- Dashboard

    def _hebrew_date_tonight(self, user: User, today: date, now: datetime) -> str | None:
        """אחרי צאת הכוכבים התאריך העברי כבר של מחר ("אור ל...")."""
        nightfall = getattr(self.rest_provider_for(user), "nightfall", None)
        if nightfall is None:
            return None
        try:
            if now >= nightfall(today):
                return day_info(today + timedelta(days=1)).hebrew_date
        except Exception:  # noqa: BLE001 - זמני היום הם תוספת תצוגה, לא סיבה להפיל את הדף
            return None
        return None

    def dashboard(self, user_id: int) -> dict:
        user = self._user(user_id)
        tz = user.timezone
        now = self.clock.now()
        today = to_local(now, tz).date()
        week_end = today + timedelta(days=6)
        prefs = self.users.preferences(user_id)

        rows = [
            r for r in self.sessions.in_range(user_id, local_datetime(today, time(0), tz),
                                              local_datetime(week_end + timedelta(days=1), time(0), tz))
            if r.status != SessionStatus.CANCELLED
        ]
        titles = {t.id: t.title for t in self.tasks.list(user_id, statuses=None)}
        load: dict[str, int] = defaultdict(int)
        for r in rows:
            if r.status in (SessionStatus.PLANNED, SessionStatus.DONE, SessionStatus.PARTIAL):
                load[to_local(r.start, tz).date().isoformat()] += _minutes(r.start, r.end)
        week = []
        for i in range(7):
            d = today + timedelta(days=i)
            info = day_info(d)
            week.append({"date": d.isoformat(), "weekday": (d.weekday() + 1) % 7, "minutes": load.get(d.isoformat(), 0),
                         "is_rest_day": info.is_rest_day, "holiday": info.holiday})

        today_sessions = [
            {"id": r.id, "task_id": r.task_id, "task_title": titles.get(r.task_id, ""), "start": r.start, "end": r.end,
             "status": r.status}
            for r in rows if to_local(r.start, tz).date() == today
        ]

        active = self.tasks.list(user_id)
        views = [self.task_service.view(t) for t in active]
        upcoming = sorted(
            (v for v in views if v.deadline and now <= v.deadline <= now + timedelta(days=7)),
            key=lambda v: v.deadline,
        )
        # מפגשים שזמנם עבר ועוד לא דווחו (בשבוע האחרון). הזמן שלהם עדיין נספר כ"נשאר" עד הדיווח.
        unreported_rows = [
            r for r in self.sessions.in_range(user_id, now - timedelta(days=7), now)
            if r.status == SessionStatus.PLANNED and r.end <= now
        ]
        unreported_by_task: dict[int, int] = defaultdict(int)
        for r in unreported_rows:
            unreported_by_task[r.task_id] += _minutes(r.start, r.end)
        unreported = [
            {"id": r.id, "task_id": r.task_id, "task_title": titles.get(r.task_id, ""), "start": r.start, "end": r.end}
            for r in sorted(unreported_rows, key=lambda r: r.start)
        ]
        needs_time = [
            v for v in views
            if v.task_type == TaskType.SCHEDULED and v.deadline and v.deadline > now
            and (v.remaining_minutes or 0) > v.scheduled_minutes + unreported_by_task.get(v.id, 0) + 15
        ]
        idle_open = [
            v for t, v in zip(active, views)
            if t.task_type == TaskType.OPEN and now - (t.last_progress_at or t.created_at) > timedelta(days=prefs.open_task_idle_days)
        ]
        overloaded = [w for w in week if w["minutes"] >= prefs.daily_max_minutes * prefs.overload_threshold]

        return {
            "today": today.isoformat(),
            "hebrew_date": day_info(today).hebrew_date,
            "hebrew_date_tonight": self._hebrew_date_tonight(user, today, now),
            "unreported_sessions": unreported,
            "today_sessions": today_sessions,
            "week": week,
            "daily_max_minutes": prefs.daily_max_minutes,
            "upcoming_deadlines": [v.model_dump(mode="json") for v in upcoming],
            "needs_scheduling": [v.model_dump(mode="json") for v in needs_time],
            "idle_open_tasks": [v.model_dump(mode="json") for v in idle_open],
            "overloaded_days": [w["date"] for w in overloaded],
            "counts": {
                "active": len(active),
                "scheduled": sum(1 for v in views if v.task_type == TaskType.SCHEDULED),
                "open": sum(1 for v in views if v.task_type == TaskType.OPEN),
                "recurring": sum(1 for v in views if v.task_type == TaskType.RECURRING),
            },
        }

    # ---------------------------------------------------------------- התקדמות

    def progress_report(self, user_id: int, days: int = 14) -> dict:
        user = self._user(user_id)
        tz = user.timezone
        now = self.clock.now()
        today = to_local(now, tz).date()
        first = today - timedelta(days=days - 1)
        start = local_datetime(first, time(0), tz)

        daily: dict[str, int] = defaultdict(int)
        for log in self.progress.for_range(user_id, start, now + timedelta(seconds=1)):
            daily[to_local(log.logged_at, tz).date().isoformat()] += log.minutes
        series = [{"date": (first + timedelta(days=i)).isoformat(), "minutes": daily.get((first + timedelta(days=i)).isoformat(), 0)}
                  for i in range(days)]

        past = [r for r in self.sessions.in_range(user_id, start, now) if r.end <= now]
        done = sum(1 for r in past if r.status in (SessionStatus.DONE, SessionStatus.PARTIAL))
        missed = sum(1 for r in past if r.status in (SessionStatus.MISSED, SessionStatus.PLANNED))

        tasks = []
        for t in self.tasks.list(user_id, statuses=(TaskStatus.ACTIVE, TaskStatus.DONE)):
            if t.task_type != TaskType.SCHEDULED:
                continue
            v = self.task_service.view(t)
            tasks.append({
                "id": t.id, "title": t.title, "status": t.status, "deadline": t.deadline,
                "estimated_minutes": t.estimated_minutes or 0, "done_minutes": v.done_minutes,
                "remaining_minutes": t.remaining_minutes or 0, "scheduled_minutes": v.scheduled_minutes,
                "postponed_count": t.postponed_count,
            })
        completed = sum(1 for t in tasks if t["status"] == TaskStatus.DONE)
        return {
            "days": days,
            "daily_minutes": series,
            "total_minutes": sum(daily.values()),
            "sessions_done": done,
            "sessions_missed": missed,
            "completion_rate": round(done / (done + missed), 3) if done + missed else None,
            "tasks": tasks,
            "tasks_completed": completed,
        }


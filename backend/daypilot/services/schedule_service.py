"""
לוח זמנים: זמינות, הצעות לשיבוץ, החלת הצעה מאושרת.

עיקרון: propose_* לא כותב שום דבר למסד. הוא מחזיר PlanProposal.
רק apply_proposal כותב, ורק אחרי אישור המשתמשת, בטרנזקציה אחת.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta
from typing import Callable, Protocol

from sqlalchemy.orm import Session

from daypilot.db.models import Proposal, ScheduledSession, Task, User
from daypilot.db.repositories.tasks import SessionRepository, TaskRepository
from daypilot.db.repositories.users import UserRepository
from daypilot.domain.enums import (
    AvailabilityKind,
    ExceptionKind,
    ProposalKind,
    ProposalStatus,
    SessionStatus,
    TaskType,
    WorkStyle,
)
from daypilot.domain.intervals import Interval, normalize, subtract, total_minutes
from daypilot.domain.schemas import (
    Alternative,
    ConflictView,
    PlanProposal,
    SessionChange,
    SessionView,
    TaskChange,
)
from daypilot.scheduling.availability import Availability, DateException, WeeklyRule, compute_availability
from daypilot.scheduling.conflicts import Conflict, capacity_conflicts, find_overlaps, overload_conflicts
from daypilot.scheduling.engine import Scheduler
from daypilot.scheduling.types import ExistingSession, PlanningInput, PlanResult, SchedulableTask, SessionRules
from daypilot.services.errors import NotFoundError, StaleProposalError, ValidationError
from daypilot.services.recurrence import Occurrence, expand_occurrences
from daypilot.utils.clock import Clock, local_datetime, to_local

MIN_HORIZON_DAYS = 7
MAX_HORIZON_DAYS = 60


class RestTimeProvider(Protocol):
    """מחזיר זמנים חסומים מסיבות דתיות (שבתות, חגים, חול המועד) בטווח תאריכים."""

    def blocked_intervals(self, first: date, last: date) -> list[Interval]: ...


@dataclass
class PlanOverrides:
    """שינויים זמניים לחישוב הצעה, לפי בקשת המשתמשת."""

    task_windows: dict[int, list[Interval]] = field(default_factory=dict)  # משימה -> רק בחלונות האלה
    daily_max_minutes: int | None = None
    extra_free: list[Interval] = field(default_factory=list)


@dataclass
class TaskSnapshot:
    """עותק של משימה לחישוב. שינויים כאן לא נוגעים במסד."""

    id: int
    title: str
    task_type: TaskType
    importance: int
    deadline: datetime | None
    remaining_minutes: int | None
    recurrence_rule: str | None
    recurrence_start: date | None
    recurrence_end: date | None
    occurrence_time: time | None
    occurrence_minutes: int | None
    prep_minutes: int | None
    work_style: WorkStyle = WorkStyle.ASSIGNMENT

    @classmethod
    def of(cls, t: Task) -> TaskSnapshot:
        return cls(
            t.id, t.title, t.task_type, t.importance, t.deadline, t.remaining_minutes, t.recurrence_rule,
            t.recurrence_start, t.recurrence_end, t.occurrence_time, t.occurrence_minutes, t.prep_minutes,
            WorkStyle(t.work_style or WorkStyle.ASSIGNMENT),
        )


@dataclass
class PlanningContext:
    user: User
    now: datetime
    first_day: date
    last_day: date
    tasks: list[TaskSnapshot]
    availability: Availability
    occurrences: list[Occurrence]
    locked: list[ScheduledSession]
    movable: list[ScheduledSession]
    rules: SessionRules


class ScheduleService:
    def __init__(
        self,
        session: Session,
        clock: Clock,
        scheduler: Scheduler,
        rest_provider_for: Callable[[User], RestTimeProvider],
        slot_minutes: int = 30,
        time_limit_s: float = 5.0,
    ):
        self.s = session
        self.clock = clock
        self.scheduler = scheduler
        self.rest_provider_for = rest_provider_for
        self.slot_minutes = slot_minutes
        self.time_limit_s = time_limit_s
        self.users = UserRepository(session)
        self.tasks = TaskRepository(session)
        self.sessions = SessionRepository(session)

    # ================= שליפה =================

    def _user(self, user_id: int) -> User:
        user = self.users.get(user_id)
        if user is None:
            raise NotFoundError(f"user {user_id} not found")
        return user

    def availability(self, user_id: int, first: date, last: date) -> Availability:
        user = self._user(user_id)
        return self._availability(user, first, last, occurrences=self._occurrences(user, self._snapshots(user.id), first, last))

    def get_schedule(self, user_id: int, start: datetime, end: datetime) -> list[SessionView]:
        rows = self.sessions.in_range(user_id, start, end)
        titles = {t.id: t.title for t in self.tasks.list(user_id, statuses=None)}
        return [
            SessionView(
                id=r.id, task_id=r.task_id, task_title=titles.get(r.task_id, ""), start=r.start, end=r.end,
                status=r.status, locked=r.locked,
            )
            for r in rows
            if r.status != SessionStatus.CANCELLED
        ]

    def fingerprint(self, user_id: int) -> str:
        """טביעת מצב: משתנה כשמשימה, מפגש, כלל או חריג משתנים."""
        tasks = self.tasks.list(user_id, statuses=None)
        now = self.clock.now()
        sessions = self.sessions.in_range(user_id, now - timedelta(days=1), now + timedelta(days=MAX_HORIZON_DAYS + 1))
        rules = self.users.rules(user_id)
        today = to_local(now).date()
        exceptions = self.users.exceptions(user_id, today, today + timedelta(days=MAX_HORIZON_DAYS + 1))
        prefs = self.users.preferences(user_id)
        payload = {
            "t": [
                [t.id, t.status, t.updated_at.isoformat(), t.remaining_minutes, t.estimated_minutes, t.importance,
                 t.deadline.isoformat() if t.deadline else None, t.recurrence_rule, t.prep_minutes, t.work_style]
                for t in tasks
            ],
            "s": [[s.id, s.start.isoformat(), s.end.isoformat(), s.status, s.locked] for s in sessions],
            "r": [[r.id, r.weekday, str(r.start_time), str(r.end_time), r.kind] for r in rules],
            "e": [[e.id, e.day.isoformat(), str(e.start_time), str(e.end_time), e.kind] for e in exceptions],
            "p": [prefs.min_session_minutes, prefs.max_session_minutes, prefs.daily_max_minutes,
                  prefs.shabbat_buffer_minutes, prefs.block_chol_hamoed],
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]

    # ================= הכנת הקשר =================

    def _snapshots(self, user_id: int) -> list[TaskSnapshot]:
        return [TaskSnapshot.of(t) for t in self.tasks.list(user_id)]

    def _occurrences(self, user: User, snaps: list[TaskSnapshot], first: date, last: date) -> list[Occurrence]:
        result: list[Occurrence] = []
        for t in snaps:
            if t.task_type != TaskType.RECURRING or not t.recurrence_rule:
                continue
            result += expand_occurrences(
                t.id, t.recurrence_rule, t.recurrence_start or first, t.recurrence_end, first, last,
                t.occurrence_time, t.occurrence_minutes, user.timezone,
            )
        return result

    def _availability(self, user: User, first: date, last: date, occurrences: list[Occurrence]) -> Availability:
        rules = [
            WeeklyRule(r.weekday, r.start_time, r.end_time, AvailabilityKind(r.kind), r.label)
            for r in self.users.rules(user.id)
        ]
        exceptions = [
            DateException(e.day, ExceptionKind(e.kind), e.start_time, e.end_time, e.label)
            for e in self.users.exceptions(user.id, first, last)
        ]
        blocked = list(self.rest_provider_for(user).blocked_intervals(first, last))
        blocked += [o.event for o in occurrences if o.event is not None]
        return compute_availability(first, last, rules, exceptions, blocked, self.clock.now(), user.timezone)

    def _context(self, user_id: int, snaps: list[TaskSnapshot] | None = None) -> PlanningContext:
        user = self._user(user_id)
        now = self.clock.now()
        snaps = snaps if snaps is not None else self._snapshots(user_id)
        today = to_local(now, user.timezone).date()
        deadlines = [to_local(t.deadline, user.timezone).date() for t in snaps if t.deadline and t.deadline > now]
        last = max([today + timedelta(days=MIN_HORIZON_DAYS)] + deadlines)
        last = min(last, today + timedelta(days=MAX_HORIZON_DAYS))
        occurrences = self._occurrences(user, snaps, today, last)
        availability = self._availability(user, today, last, occurrences)

        horizon_end = local_datetime(last + timedelta(days=1), time(0), user.timezone)
        rows = self.sessions.in_range(user_id, now, horizon_end)
        locked: list[ScheduledSession] = []
        movable: list[ScheduledSession] = []
        for r in rows:
            if r.status == SessionStatus.CANCELLED:
                continue
            if r.status == SessionStatus.PLANNED and not r.locked and r.start >= now:
                movable.append(r)
            else:
                locked.append(r)

        prefs = self.users.preferences(user_id)
        rules = SessionRules(
            min_session_minutes=prefs.min_session_minutes,
            max_session_minutes=prefs.max_session_minutes,
            daily_max_minutes=prefs.daily_max_minutes,
            slot_minutes=self.slot_minutes,
        )
        return PlanningContext(user, now, today, last, snaps, availability, occurrences, locked, movable, rules)

    # ================= חישוב הצעה =================

    def _build_input(self, ctx: PlanningContext, overrides: PlanOverrides) -> tuple[PlanningInput, dict[int, tuple[int, date | None]]]:
        tz = ctx.user.timezone
        locked_by_task: dict[tuple[int, date | None], int] = defaultdict(int)
        locked_by_day: dict[str, int] = defaultdict(int)
        planned_locked = [r for r in ctx.locked if r.status == SessionStatus.PLANNED and r.end > ctx.now]
        for r in planned_locked:
            minutes = int((r.end - r.start).total_seconds() // 60)
            locked_by_task[(r.task_id, r.occurrence_date)] += minutes
        for r in ctx.locked:
            if r.status in (SessionStatus.PLANNED, SessionStatus.DONE, SessionStatus.PARTIAL):
                locked_by_day[to_local(r.start, tz).date().isoformat()] += int((r.end - r.start).total_seconds() // 60)

        free = subtract(ctx.availability.free, [Interval(r.start, r.end) for r in ctx.locked if r.status != SessionStatus.CANCELLED])
        if overrides.extra_free:
            free = normalize(free + subtract(overrides.extra_free, ctx.availability.busy))

        id_map: dict[int, tuple[int, date | None]] = {}
        sched: list[SchedulableTask] = []
        horizon_end = local_datetime(ctx.last_day + timedelta(days=1), time(0), tz)

        def windows_for(task_id: int) -> list[Interval] | None:
            return overrides.task_windows.get(task_id)

        for t in ctx.tasks:
            if t.task_type != TaskType.SCHEDULED or not t.deadline or not t.remaining_minutes:
                continue
            if t.deadline <= ctx.now:
                continue
            need = t.remaining_minutes - locked_by_task.get((t.id, None), 0)
            if need <= 0:
                continue
            id_map[t.id] = (t.id, None)
            sched.append(
                SchedulableTask(t.id, t.title, need, min(t.deadline, horizon_end), t.importance, allowed=windows_for(t.id),
                                style=t.work_style)
            )

        snap_by_id = {t.id: t for t in ctx.tasks}
        synthetic = -1
        for occ in ctx.occurrences:
            t = snap_by_id[occ.task_id]
            if not t.prep_minutes or occ.deadline <= ctx.now:
                continue
            need = t.prep_minutes - locked_by_task.get((t.id, occ.day), 0)
            if need <= 0:
                continue
            id_map[synthetic] = (t.id, occ.day)
            earliest = occ.deadline - timedelta(days=7)
            sched.append(
                SchedulableTask(synthetic, f"{t.title} ({occ.day.isoformat()})", need, occ.deadline, t.importance,
                                earliest_start=earliest, allowed=windows_for(t.id))
            )
            synthetic -= 1

        reverse = {v: k for k, v in id_map.items()}
        previous = [
            ExistingSession(reverse[(r.task_id, r.occurrence_date)], r.start, r.end, False, r.id)
            for r in ctx.movable
            if (r.task_id, r.occurrence_date) in reverse
        ]
        rules = ctx.rules
        if overrides.daily_max_minutes:
            rules = replace(rules, daily_max_minutes=overrides.daily_max_minutes)
        data = PlanningInput(
            now=ctx.now, free=free, preferred=ctx.availability.preferred, tasks=sched, rules=rules,
            previous_sessions=previous, locked_minutes_by_day=dict(locked_by_day), tz_name=tz,
            time_limit_s=self.time_limit_s,
        )
        return data, id_map

    def propose(
        self,
        user_id: int,
        kind: ProposalKind,
        summary: str,
        task_ids: list[int] | None = None,
        overrides: PlanOverrides | None = None,
        task_changes: list[TaskChange] | None = None,
    ) -> PlanProposal:
        overrides = overrides or PlanOverrides()
        task_changes = task_changes or []
        fingerprint = self.fingerprint(user_id)
        snaps = self._apply_changes_to_snapshots(user_id, self._snapshots(user_id), task_changes)
        ctx = self._context(user_id, snaps)
        data, id_map = self._build_input(ctx, overrides)
        result = self.scheduler.plan(data)

        add, remove = self._diff(ctx, result, id_map)
        conflicts = self._conflicts(ctx, result, id_map, data.rules.daily_max_minutes)
        feasible = result.is_complete
        alternatives = [] if feasible else self._alternatives(ctx, overrides, result, id_map)
        focus = task_ids or sorted({c.task_id for c in task_changes} | {a.task_id for a in add})
        return PlanProposal(
            id=uuid.uuid4().hex,
            kind=kind,
            summary=summary,
            task_ids=focus,
            add_sessions=add,
            remove_session_ids=remove,
            task_changes=task_changes,
            conflicts=conflicts,
            alternatives=alternatives,
            feasible=feasible,
            moved_minutes=result.moved_minutes,
            fingerprint=fingerprint,
            created_at=ctx.now,
        )

    def _apply_changes_to_snapshots(self, user_id: int, snaps: list[TaskSnapshot], changes: list[TaskChange]) -> list[TaskSnapshot]:
        by_id = {s.id: s for s in snaps}
        for ch in changes:
            snap = by_id.get(ch.task_id)
            if snap is None:
                raise NotFoundError(f"task {ch.task_id} not found or not active", task_id=ch.task_id)
            if ch.delete:
                by_id.pop(ch.task_id)
                continue
            if ch.deadline is not None:
                if ch.deadline <= self.clock.now():
                    raise ValidationError("new deadline is in the past")
                snap.deadline = ch.deadline
            if ch.remaining_minutes is not None:
                snap.remaining_minutes = ch.remaining_minutes
            elif ch.estimated_minutes is not None:
                task = self.tasks.get(user_id, ch.task_id)
                done = (task.estimated_minutes or 0) - (task.remaining_minutes or 0)
                snap.remaining_minutes = max(0, ch.estimated_minutes - done)
        return list(by_id.values())

    def _diff(self, ctx: PlanningContext, result: PlanResult, id_map) -> tuple[list[SessionChange], list[int]]:
        planned = []
        for p in result.sessions:
            task_id, occ = id_map[p.task_id]
            planned.append(SessionChange(task_id=task_id, start=p.start, end=p.end, occurrence_date=occ))
        existing = {(r.task_id, r.occurrence_date, r.start, r.end): r.id for r in ctx.movable}
        new_keys = {(c.task_id, c.occurrence_date, c.start, c.end) for c in planned}
        add = [c for c in planned if (c.task_id, c.occurrence_date, c.start, c.end) not in existing]
        remove = [sid for key, sid in existing.items() if key not in new_keys]
        return add, sorted(remove)

    def _conflicts(self, ctx: PlanningContext, result: PlanResult, id_map, daily_max: int) -> list[ConflictView]:
        found: list[Conflict] = []
        found += find_overlaps(
            [ExistingSession(r.task_id, r.start, r.end, True, r.id) for r in ctx.locked if r.status == SessionStatus.PLANNED],
            ctx.availability.busy,
        )
        shortfalls = [replace(s, task_id=id_map[s.task_id][0]) for s in result.shortfalls]
        found += capacity_conflicts(shortfalls)
        final = [ExistingSession(id_map[p.task_id][0], p.start, p.end) for p in result.sessions]
        final += [
            ExistingSession(r.task_id, r.start, r.end, True, r.id)
            for r in ctx.locked
            if r.status in (SessionStatus.PLANNED, SessionStatus.DONE, SessionStatus.PARTIAL)
        ]
        found += overload_conflicts(final, daily_max, ctx.user.timezone, threshold=self.users.preferences(ctx.user.id).overload_threshold)
        return [ConflictView(kind=c.kind, task_ids=list(c.task_ids), message=c.message, details=c.details) for c in found]

    def _alternatives(self, ctx: PlanningContext, overrides: PlanOverrides, base: PlanResult, id_map) -> list[Alternative]:
        """כשאין מספיק זמן: בודק מה באמת יפתור, ומחזיר רק עובדות מחושבות."""
        base_missing = sum(s.missing_minutes for s in base.shortfalls)
        options: list[tuple[str, str, PlanOverrides, list[TaskSnapshot] | None]] = []

        options.append((
            "raise_daily_max",
            f"העלאת התקרה היומית בשעתיים (ל-{(ctx.rules.daily_max_minutes + 120) / 60:g} שעות)",
            replace(overrides, daily_max_minutes=ctx.rules.daily_max_minutes + 120),
            None,
        ))

        extra: list[Interval] = []
        by_day: dict[date, datetime] = {}
        for iv in ctx.availability.active:
            day = to_local(iv.start, ctx.user.timezone).date()
            by_day[day] = max(by_day.get(day, iv.end), iv.end)
        for end in by_day.values():
            extra.append(Interval(end, end + timedelta(hours=1)))
        options.append(("extend_evenings", "הוספת שעה אחרי סוף שעות הפעילות בכל יום", replace(overrides, extra_free=overrides.extra_free + extra), None))

        short_ids = {id_map[s.task_id][0] for s in base.shortfalls if s.missing_minutes}
        others = sorted(
            (t for t in ctx.tasks if t.id not in short_ids and t.task_type == TaskType.SCHEDULED and t.remaining_minutes),
            key=lambda t: (t.importance, -(t.deadline.timestamp() if t.deadline else 0)),
        )
        if others:
            drop = others[0]
            options.append((
                f"postpone_task:{drop.id}",
                f"דחייה או ויתור על המשימה '{drop.title}' (חשיבות נמוכה יותר)",
                overrides,
                [t for t in ctx.tasks if t.id != drop.id],
            ))

        result: list[Alternative] = []
        fast = min(self.time_limit_s, 2.0)
        for key, description, ov, snaps in options:
            alt_ctx = ctx if snaps is None else replace(ctx, tasks=snaps)
            data, alt_map = self._build_input(alt_ctx, ov)
            data.time_limit_s = fast
            res = self.scheduler.plan(data)
            missing = sum(s.missing_minutes for s in res.shortfalls if alt_map[s.task_id][0] in short_ids)
            result.append(Alternative(key=key, description=description, resolves=missing == 0, missing_minutes=missing))
        result.sort(key=lambda a: (not a.resolves, a.missing_minutes))
        return [a for a in result if a.missing_minutes < base_missing]

    # ================= החלת הצעה מאושרת =================

    def apply_proposal(self, user_id: int, proposal: PlanProposal, thread_id: str = "") -> dict:
        """כותב הצעה מאושרת. אידמפוטנטי: הרצה חוזרת של אותה הצעה לא כותבת שוב."""
        if self.sessions.plan_version_for_proposal(user_id, proposal.id):
            return {"status": "already_applied", "proposal_id": proposal.id}
        if proposal.fingerprint != self.fingerprint(user_id):
            raise StaleProposalError("data changed since the proposal was computed; recompute it", proposal_id=proposal.id)

        now = self.clock.now()
        for ch in proposal.task_changes:
            task = self.tasks.get(user_id, ch.task_id)
            if task is None:
                raise NotFoundError(f"task {ch.task_id} not found", task_id=ch.task_id)
            if ch.delete:
                self.tasks.delete(task)
                continue
            if ch.deadline is not None:
                if task.deadline and ch.deadline > task.deadline:
                    task.postponed_count += 1
                task.deadline = ch.deadline
            if ch.estimated_minutes is not None:
                done = (task.estimated_minutes or 0) - (task.remaining_minutes or 0)
                task.estimated_minutes = ch.estimated_minutes
                task.remaining_minutes = max(0, ch.estimated_minutes - done)
            if ch.remaining_minutes is not None:
                task.remaining_minutes = ch.remaining_minutes
            task.updated_at = now

        removable = [
            r.id for r in (self.sessions.get(user_id, sid) for sid in proposal.remove_session_ids)
            if r is not None and r.status == SessionStatus.PLANNED and not r.locked
        ]
        self.sessions.delete_ids(user_id, removable)

        version = self.sessions.add_plan_version(user_id, proposal.summary[:300], proposal.id, now)
        deleted = {c.task_id for c in proposal.task_changes if c.delete}
        self.sessions.add_many([
            ScheduledSession(
                user_id=user_id, task_id=c.task_id, start=c.start, end=c.end, status=SessionStatus.PLANNED,
                locked=False, occurrence_date=c.occurrence_date, plan_version_id=version.id, created_at=now,
            )
            for c in proposal.add_sessions
            if c.task_id not in deleted
        ])
        self.record_decision(user_id, proposal, ProposalStatus.APPROVED, thread_id)
        return {
            "status": "applied",
            "proposal_id": proposal.id,
            "added_sessions": len(proposal.add_sessions),
            "removed_sessions": len(removable),
            "task_changes": len(proposal.task_changes),
        }

    def record_decision(self, user_id: int, proposal: PlanProposal, status: ProposalStatus, thread_id: str = "") -> None:
        existing = self.s.get(Proposal, proposal.id)
        if existing:
            existing.status = status
            existing.decided_at = self.clock.now()
            return
        self.s.add(
            Proposal(
                id=proposal.id, user_id=user_id, thread_id=thread_id, kind=proposal.kind, status=status,
                summary=proposal.summary, payload=json.loads(proposal.model_dump_json()),
                created_at=proposal.created_at, decided_at=self.clock.now(),
            )
        )
        self.s.flush()


def minutes_of(sessions: list[SessionChange]) -> int:
    return total_minutes([Interval(s.start, s.end) for s in sessions])

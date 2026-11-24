"""
תרגום קריאת propose_* להצעה מחושבת, ותצוגה של הצעה למשתמשת.

המודל רק בוחר כלי וארגומנטים. החישוב עצמו (שיבוץ, התנגשויות, חלופות) נעשה בקוד.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import time, timedelta

from daypilot.agent.dates import HEBREW_WEEKDAYS, il_weekday, parse_local_datetime
from daypilot.container import AppContainer
from daypilot.domain.enums import ConflictKind, ProposalKind
from daypilot.domain.intervals import Interval
from daypilot.domain.schemas import PlanProposal, TaskChange
from daypilot.services.errors import ValidationError
from daypilot.services.schedule_service import PlanOverrides
from daypilot.domain.intervals import intersect
from daypilot.utils.clock import local_datetime, to_local

KIND_BY_TOOL = {
    "propose_schedule": ProposalKind.SCHEDULE,
    "propose_reschedule": ProposalKind.RESCHEDULE,
    "propose_deadline_change": ProposalKind.DEADLINE_CHANGE,
    "propose_duration_change": ProposalKind.DURATION_CHANGE,
    "propose_delete_task": ProposalKind.DELETE_TASK,
}


def daily_windows(spec: dict, tz: str, today, days: int = 60) -> list[Interval]:
    """{"from": "17:00", "to": "22:00"} -> חלון כזה בכל יום באופק התכנון."""
    try:
        start_t = time.fromisoformat(str(spec.get("from", "")))
        end_t = time.fromisoformat(str(spec.get("to", "")))
    except ValueError as exc:
        raise ValidationError("daily_time_window needs from/to as HH:MM") from exc
    if end_t <= start_t:
        raise ValidationError("daily_time_window 'to' must be after 'from'")
    return [
        Interval(local_datetime(today + timedelta(days=i), start_t, tz), local_datetime(today + timedelta(days=i), end_t, tz))
        for i in range(days)
    ]


def compute_proposal(container: AppContainer, user_id: int, tool_name: str, args: dict) -> PlanProposal:
    tz = container.settings.timezone
    kind = KIND_BY_TOOL[tool_name]
    reason = str(args.get("reason") or "")[:300]
    overrides = PlanOverrides()
    changes: list[TaskChange] = []
    task_ids: list[int] | None = None

    today = to_local(container.clock.now(), tz).date()
    day_windows = daily_windows(args["daily_time_window"], tz, today) if args.get("daily_time_window") else None

    if kind == ProposalKind.SCHEDULE:
        task_ids = [int(t) for t in (args.get("task_ids") or [])] or None
        if day_windows:
            if not task_ids:
                with container.unit() as svc:
                    task_ids = [t.id for t in svc.tasks.list(user_id)]
            overrides.task_windows = {tid: day_windows for tid in task_ids}
    elif kind == ProposalKind.RESCHEDULE:
        task_ids = [int(t) for t in (args.get("task_ids") or [])]
        if not task_ids:
            raise ValidationError("task_ids is required")
        windows = []
        for w in args.get("allowed_windows") or []:
            start, _ = parse_local_datetime(str(w.get("start", "")), tz)
            end, end_date_only = parse_local_datetime(str(w.get("end", "")), tz)
            if end_date_only:
                end = end + timedelta(days=1)  # תאריך סיום בלבד = עד סוף אותו יום
            if end <= start:
                raise ValidationError("each window must end after it starts")
            windows.append(Interval(start, end))
        if windows and day_windows:
            windows = intersect(windows, day_windows)
            if not windows:
                raise ValidationError("allowed_windows and daily_time_window do not overlap")
        elif day_windows:
            windows = day_windows
        if windows:
            overrides.task_windows = {tid: windows for tid in task_ids}
        if args.get("daily_max_minutes"):
            overrides.daily_max_minutes = int(args["daily_max_minutes"])
    elif kind == ProposalKind.DEADLINE_CHANGE:
        deadline, _ = parse_local_datetime(str(args.get("new_deadline", "")), tz)
        changes = [TaskChange(task_id=int(args["task_id"]), deadline=deadline)]
    elif kind == ProposalKind.DURATION_CHANGE:
        minutes = int(args.get("new_estimated_minutes", 0))
        if minutes < 5:
            raise ValidationError("new_estimated_minutes must be at least 5")
        changes = [TaskChange(task_id=int(args["task_id"]), estimated_minutes=minutes)]
    elif kind == ProposalKind.DELETE_TASK:
        changes = [TaskChange(task_id=int(args["task_id"]), delete=True)]

    with container.unit() as svc:
        for tid in (task_ids or []) + [c.task_id for c in changes]:
            svc.tasks.get(user_id, tid)  # NotFoundError אם לא קיימת
        return svc.schedule.propose(user_id, kind, reason, task_ids, overrides, changes)


def has_changes(p: PlanProposal) -> bool:
    return bool(p.add_sessions or p.remove_session_ids or p.task_changes)


def proposal_for_model(p: PlanProposal, titles: dict[int, str], tz: str) -> dict:
    """תקציר קומפקטי להודעת הכלי שהמודל קורא."""
    by_task: dict[int, int] = defaultdict(int)
    by_day: dict = defaultdict(list)
    for s in sorted(p.add_sessions, key=lambda x: x.start):
        by_task[s.task_id] += int((s.end - s.start).total_seconds() // 60)
        start = to_local(s.start, tz)
        by_day[start.date()].append(f"{start:%H:%M}-{to_local(s.end, tz):%H:%M} {titles.get(s.task_id, '')}".strip())
    days = sorted(by_day)
    return {
        "proposal_id": p.id,
        "kind": p.kind,
        "feasible": p.feasible,
        "new_sessions": len(p.add_sessions),
        "removed_sessions": len(p.remove_session_ids),
        "new_minutes_by_task": {titles.get(k, str(k)): v for k, v in by_task.items()},
        # הימים והשעות בדיוק כפי שנקבעו: המודל מסכם רק מתוכם, בלי לנחש תאריכים
        "new_sessions_by_day": [
            {"date": d.isoformat(), "weekday": HEBREW_WEEKDAYS[il_weekday(d)], "sessions": by_day[d]} for d in days
        ],
        "first_session_date": days[0].isoformat() if days else None,
        "last_session_date": days[-1].isoformat() if days else None,
        "task_changes": [c.model_dump(mode="json", exclude_none=True) for c in p.task_changes],
        "conflicts": [c.model_dump(mode="json") for c in p.conflicts],
        "alternatives": [a.model_dump(mode="json") for a in p.alternatives],
    }


def format_proposal(p: PlanProposal, titles: dict[int, str], tz: str) -> str:
    """תצוגה בעברית למשתמשת (CLI, ובהמשך גם בממשק)."""
    lines: list[str] = []
    if p.summary:
        lines.append(f"הצעה: {p.summary}")
    for ch in p.task_changes:
        name = titles.get(ch.task_id, f"משימה {ch.task_id}")
        if ch.delete:
            lines.append(f"• מחיקת המשימה '{name}' וכל המפגשים שלה")
        if ch.deadline:
            lines.append(f"• מועד יעד חדש ל'{name}': {to_local(ch.deadline, tz):%d.%m.%Y %H:%M}")
        if ch.estimated_minutes:
            lines.append(f"• משך עבודה חדש ל'{name}': {ch.estimated_minutes / 60:g} שעות")

    if p.add_sessions:
        lines.append("מפגשים חדשים:")
        by_day: dict = defaultdict(list)
        for s in sorted(p.add_sessions, key=lambda x: x.start):
            by_day[to_local(s.start, tz).date()].append(s)
        for day, items in by_day.items():
            parts = [
                f"{to_local(s.start, tz):%H:%M}-{to_local(s.end, tz):%H:%M} {titles.get(s.task_id, '')}" for s in items
            ]
            lines.append(f"  יום {HEBREW_WEEKDAYS[il_weekday(day)]} {day:%d.%m}: " + ", ".join(parts))
    if p.remove_session_ids:
        lines.append(f"מפגשים שיוזזו או יבוטלו: {len(p.remove_session_ids)}")

    for c in p.conflicts:
        if c.kind == ConflictKind.CAPACITY:
            missing = c.details.get("missing_minutes", 0)
            names = ", ".join(titles.get(t, str(t)) for t in c.task_ids)
            lines.append(f"⚠ אין מספיק זמן ל'{names}': חסרות {missing / 60:g} שעות לפני מועד היעד")
        elif c.kind == ConflictKind.OVERLOAD:
            lines.append(f"⚠ יום עמוס: {c.details.get('day')} ({c.details.get('minutes', 0) / 60:g} שעות)")
        else:
            lines.append(f"⚠ התנגשות: {c.message}")
    for a in p.alternatives:
        status = "פותר" if a.resolves else f"נשארות חסרות {a.missing_minutes / 60:g} שעות"
        lines.append(f"  חלופה: {a.description} ({status})")
    return "\n".join(lines) if lines else "אין שינויים"

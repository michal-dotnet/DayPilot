"""
הכלים של האגנט.

שלוש קבוצות:
- קריאה: מחזירים נתונים מהמסד.
- כתיבה אוטומטית: מותרים לפי המדיניות (משימה חדשה, פרטים פשוטים, התקדמות, הגדרות).
- הצעה (propose_*): לא מתבצעים ב-ToolNode. הגרף מנתב אותם ל-build_proposal,
  מחשב הצעה ועוצר לאישור. לכן הגוף שלהם לא אמור לרוץ לעולם.

כל כלי פותח טרנזקציה משלו דרך AppContainer.unit(), כך שכתיבה נשמרת או מתבטלת בשלמותה.
"""


from datetime import time, timedelta
from typing import Annotated, Literal

from dateutil.rrule import rrulestr
from langchain_core.tools import BaseTool, tool
from langgraph.prebuilt import InjectedState

from daypilot.agent.dates import parse_date, parse_local_datetime, resolve_hebrew
from daypilot.agent.tools.common import dumps, error, safe_tool
from daypilot.container import AppContainer
from daypilot.domain.enums import AvailabilityKind, ExceptionKind, SessionStatus, TaskType, WorkStyle
from daypilot.domain.intervals import Interval, subtract, total_minutes
from daypilot.domain.schemas import (
    DateExceptionIn,
    PreferencesUpdate,
    ProgressReport,
    TaskCreate,
    TaskDetailsUpdate,
    WeeklyRuleIn,
)
from daypilot.utils.clock import local_datetime, to_local

UserId = Annotated[int, InjectedState("user_id")]

PROPOSAL_TOOL_NAMES = {
    "propose_schedule",
    "propose_reschedule",
    "propose_deadline_change",
    "propose_duration_change",
    "propose_delete_task",
}


def _tz(container: AppContainer) -> str:
    return container.settings.timezone


def build_tools(container: AppContainer) -> list[BaseTool]:
    tz = _tz(container)

    def today():
        return to_local(container.clock.now(), tz).date()

    # ---------------- קריאה ----------------

    @tool
    @safe_tool
    def list_tasks(user_id: UserId, include_done: bool = False) -> str:
        """List the user's tasks with status, deadline, remaining and scheduled minutes."""
        with container.unit() as svc:
            return dumps([svc.tasks.view(t).model_dump() for t in svc.tasks.list(user_id, include_done)])

    @tool
    @safe_tool
    def find_tasks(user_id: UserId, text: str) -> str:
        """Find active tasks whose title contains the given text. Use it to resolve which task the user means."""
        with container.unit() as svc:
            found = svc.tasks.tasks.find_by_title(user_id, text)
            return dumps([svc.tasks.view(t).model_dump() for t in found])

    @tool
    @safe_tool
    def get_schedule(user_id: UserId, start_date: str, end_date: str) -> str:
        """Get planned work sessions between two dates (inclusive, YYYY-MM-DD), plus blocked times (Shabbat, holidays, classes)."""
        first, last = parse_date(start_date), parse_date(end_date)
        if last < first or (last - first).days > 31:
            return error("range must be 0-31 days and end after start")
        start = local_datetime(first, time(0), tz)
        end = local_datetime(last + timedelta(days=1), time(0), tz)
        with container.unit() as svc:
            sessions = svc.schedule.get_schedule(user_id, start, end)
            av = svc.schedule.availability(user_id, first, last)
            return dumps({
                "sessions": [s.model_dump() for s in sessions],
                "busy": [{"start": b.start, "end": b.end} for b in av.busy if b.end > start and b.start < end],
            })

    @tool
    @safe_tool
    def check_availability(user_id: UserId, start_date: str, end_date: str) -> str:
        """Free time per day between two dates (inclusive, YYYY-MM-DD), after classes, commitments, Shabbat/holidays and existing sessions."""
        first, last = parse_date(start_date), parse_date(end_date)
        if last < first or (last - first).days > 31:
            return error("range must be 0-31 days and end after start")
        with container.unit() as svc:
            av = svc.schedule.availability(user_id, first, last)
            start = local_datetime(first, time(0), tz)
            end = local_datetime(last + timedelta(days=1), time(0), tz)
            taken = [
                s for s in svc.schedule.get_schedule(user_id, start, end) if s.status == SessionStatus.PLANNED
            ]
            free = subtract(av.free, [Interval(s.start, s.end) for s in taken])
            per_day: dict[str, list[Interval]] = {}
            for iv in free:
                per_day.setdefault(to_local(iv.start, tz).date().isoformat(), []).append(iv)
            return dumps({
                "total_free_minutes": total_minutes(free),
                "days": {
                    d: {"free_minutes": total_minutes(ws), "windows": [{"start": w.start, "end": w.end} for w in ws]}
                    for d, ws in per_day.items()
                },
            })

    @tool
    @safe_tool
    def get_progress_summary(user_id: UserId, days: int = 7) -> str:
        """Progress over the last N days: minutes logged per task, done/missed sessions, and tasks with no progress."""
        days = max(1, min(days, 60))
        with container.unit() as svc:
            now = container.clock.now()
            start = now - timedelta(days=days)
            logs = svc.tasks.progress.for_range(user_id, start, now)
            sessions = svc.schedule.get_schedule(user_id, start, now)
            per_task: dict[int, int] = {}
            for log in logs:
                per_task[log.task_id] = per_task.get(log.task_id, 0) + log.minutes
            tasks = {t.id: t for t in svc.tasks.list(user_id, include_done=True)}
            return dumps({
                "days": days,
                "minutes_by_task": [
                    {"task_id": tid, "title": tasks[tid].title if tid in tasks else "", "minutes": m}
                    for tid, m in per_task.items()
                ],
                "sessions_done": sum(1 for s in sessions if s.status in (SessionStatus.DONE, SessionStatus.PARTIAL)),
                "sessions_missed": sum(1 for s in sessions if s.status == SessionStatus.MISSED),
                "postponed_often": [
                    {"task_id": t.id, "title": t.title, "postponed": t.postponed_count}
                    for t in tasks.values() if t.postponed_count >= 3 and t.status == "active"
                ],
            })

    @tool
    @safe_tool
    def get_settings(user_id: UserId) -> str:
        """Get preferences, weekly rules (classes, work, active and preferred hours) and upcoming date exceptions."""
        with container.unit() as svc:
            user = svc.settings.users.get(user_id)
            prefs = svc.settings.preferences(user_id)
            rules = svc.settings.users.rules(user_id)
            exceptions = svc.settings.users.exceptions(user_id, today(), today() + timedelta(days=60))
            return dumps({
                "city": user.city.key if user and user.city else None,
                "preferences": {
                    "min_session_minutes": prefs.min_session_minutes,
                    "max_session_minutes": prefs.max_session_minutes,
                    "daily_max_minutes": prefs.daily_max_minutes,
                    "shabbat_buffer_minutes": prefs.shabbat_buffer_minutes,
                    "block_chol_hamoed": prefs.block_chol_hamoed,
                },
                "weekly_rules": [
                    {"id": r.id, "weekday": r.weekday, "start": str(r.start_time)[:5], "end": str(r.end_time)[:5],
                     "kind": r.kind, "label": r.label}
                    for r in rules
                ],
                "exceptions": [
                    {"id": e.id, "day": e.day, "start": str(e.start_time)[:5] if e.start_time else None,
                     "end": str(e.end_time)[:5] if e.end_time else None, "kind": e.kind, "label": e.label}
                    for e in exceptions
                ],
                "weekday_numbers": "0=Sunday ... 6=Saturday",
            })

    @tool
    @safe_tool
    def resolve_hebrew_date(day: int, month: str, year: int | None = None) -> str:
        """Convert a Hebrew date to a Gregorian date. month in Hebrew (e.g. 'שבט', 'אדר ב'). Without year: the next upcoming one."""
        return dumps({"date": resolve_hebrew(day, month, today(), year)})

    # ---------------- כתיבה אוטומטית ----------------

    @tool
    @safe_tool
    def create_task(
        user_id: UserId,
        title: str,
        task_type: Literal["scheduled", "open", "recurring"],
        deadline: str | None = None,
        estimated_minutes: int | None = None,
        importance: int = 3,
        work_style: Literal["assignment", "exam"] = "assignment",
        description: str = "",
        recurrence_rule: str | None = None,
        occurrence_time: str | None = None,
        occurrence_minutes: int | None = None,
        prep_minutes: int | None = None,
        assumptions: list[str] | None = None,
    ) -> str:
        """Create a task. scheduled: needs deadline (ISO) and estimated_minutes. open: no deadline.
        recurring: needs recurrence_rule (RRULE like FREQ=WEEKLY;BYDAY=WE) and occurrence_time (HH:MM) + occurrence_minutes
        for a fixed event and/or prep_minutes of work before each occurrence. importance 1-5.
        work_style (scheduled tasks): exam = studying for an exam/test/quiz (ramps up, full day right before);
        assignment = homework, paper, project, presentation, reading or any other work (kept to as few days as possible).
        Put defaults you chose in assumptions. The task is NOT scheduled yet: call propose_schedule afterwards."""
        notes = list(assumptions or [])
        parsed_deadline = None
        if deadline:
            parsed_deadline, date_only = parse_local_datetime(deadline, tz)
            if date_only:
                notes.append("deadline given as a date only: work must be finished by the start of that day")
        occ_time = None
        if occurrence_time:
            occ_time = time.fromisoformat(occurrence_time)
        if recurrence_rule:
            try:
                rrulestr(recurrence_rule)
            except (ValueError, TypeError) as exc:
                return error(f"invalid recurrence_rule: {exc}")
        data = TaskCreate(
            title=title, task_type=TaskType(task_type), description=description, deadline=parsed_deadline,
            estimated_minutes=estimated_minutes, importance=importance, work_style=WorkStyle(work_style),
            recurrence_rule=recurrence_rule,
            occurrence_time=occ_time, occurrence_minutes=occurrence_minutes, prep_minutes=prep_minutes,
            assumptions=notes,
        )
        with container.unit() as svc:
            task = svc.tasks.create(user_id, data)
            return dumps({"ok": True, "task": svc.tasks.view(task).model_dump(), "scheduled": False})

    @tool
    @safe_tool
    def update_task_details(
        user_id: UserId,
        task_id: int,
        title: str | None = None,
        description: str | None = None,
        importance: int | None = None,
        work_style: Literal["assignment", "exam"] | None = None,
    ) -> str:
        """Update a task's title, description, importance (1-5) or work_style. Does not change the schedule:
        a new work_style applies to the next proposal."""
        with container.unit() as svc:
            task = svc.tasks.update_details(
                user_id,
                task_id,
                TaskDetailsUpdate(
                    title=title, description=description, importance=importance,
                    work_style=WorkStyle(work_style) if work_style else None,
                ),
            )
            return dumps({"ok": True, "task": svc.tasks.view(task).model_dump()})

    @tool
    @safe_tool
    def log_progress(user_id: UserId, task_id: int, minutes: int, note: str = "", completed: bool = False,
                     session_id: int | None = None) -> str:
        """Record work actually done on a task (minutes). completed=true marks the task done."""
        with container.unit() as svc:
            task = svc.tasks.log_progress(
                user_id, ProgressReport(task_id=task_id, minutes=minutes, note=note, completed=completed, session_id=session_id)
            )
            return dumps({"ok": True, "task": svc.tasks.view(task).model_dump()})

    @tool
    @safe_tool
    def mark_task_done(user_id: UserId, task_id: int) -> str:
        """Mark a task as completed. Its future sessions are released."""
        with container.unit() as svc:
            task = svc.tasks.mark_done(user_id, task_id)
            return dumps({"ok": True, "task": svc.tasks.view(task).model_dump()})

    @tool
    @safe_tool
    def update_preferences(
        user_id: UserId,
        min_session_minutes: int | None = None,
        max_session_minutes: int | None = None,
        daily_max_minutes: int | None = None,
        city_key: str | None = None,
    ) -> str:
        """Change session length limits, daily maximum work minutes, or city (e.g. jerusalem, bnei_brak, haifa)."""
        with container.unit() as svc:
            svc.settings.update_preferences(
                user_id,
                PreferencesUpdate(min_session_minutes=min_session_minutes, max_session_minutes=max_session_minutes,
                                  daily_max_minutes=daily_max_minutes, city_key=city_key),
            )
            return dumps({"ok": True, "note": "saved; existing sessions are unchanged until a new schedule is proposed"})

    @tool
    @safe_tool
    def add_weekly_rule(
        user_id: UserId,
        weekday: int,
        start_time: str,
        end_time: str,
        kind: Literal["active_hours", "preferred_study", "class", "work", "commitment"],
        label: str = "",
    ) -> str:
        """Add a fixed weekly rule. weekday 0=Sunday..6=Saturday, times HH:MM.
        active_hours = when work may be scheduled at all; preferred_study = preferred study hours;
        class/work/commitment = busy time."""
        data = WeeklyRuleIn(weekday=weekday, start_time=time.fromisoformat(start_time), end_time=time.fromisoformat(end_time),
                            kind=AvailabilityKind(kind), label=label)
        with container.unit() as svc:
            rule = svc.settings.add_rule(user_id, data)
            return dumps({"ok": True, "rule_id": rule.id})

    @tool
    @safe_tool
    def remove_weekly_rule(user_id: UserId, rule_id: int) -> str:
        """Remove a weekly rule by id (see get_settings)."""
        with container.unit() as svc:
            svc.settings.delete_rule(user_id, rule_id)
            return dumps({"ok": True})

    @tool
    @safe_tool
    def add_date_exception(
        user_id: UserId,
        day: str,
        kind: Literal["blocked", "extra_available"],
        start_time: str | None = None,
        end_time: str | None = None,
        label: str = "",
    ) -> str:
        """Mark a specific date as unavailable (blocked) or with extra free time. Without times = the whole day."""
        data = DateExceptionIn(
            day=parse_date(day), kind=ExceptionKind(kind),
            start_time=time.fromisoformat(start_time) if start_time else None,
            end_time=time.fromisoformat(end_time) if end_time else None, label=label,
        )
        with container.unit() as svc:
            ex = svc.settings.add_exception(user_id, data)
            return dumps({"ok": True, "exception_id": ex.id})

    @tool
    @safe_tool
    def remove_date_exception(user_id: UserId, exception_id: int) -> str:
        """Remove a date exception by id."""
        with container.unit() as svc:
            svc.settings.delete_exception(user_id, exception_id)
            return dumps({"ok": True})

    # ---------------- הצעות (דורשות אישור) ----------------

    @tool
    def propose_schedule(reason: str, task_ids: list[int] | None = None, daily_time_window: dict | None = None) -> str:
        """Compute a schedule proposal: place work sessions for the given tasks (or all tasks that need time).
        daily_time_window: optional {"from": "HH:MM", "to": "HH:MM"} to place these tasks only in that time of day,
        every day (e.g. evenings {"from": "17:00", "to": "22:00"}).
        Existing sessions move only if needed. The user must approve before anything is saved."""
        raise RuntimeError("handled by the graph")

    @tool
    def propose_reschedule(
        reason: str,
        task_ids: list[int],
        allowed_windows: list[dict] | None = None,
        daily_time_window: dict | None = None,
        daily_max_minutes: int | None = None,
    ) -> str:
        """Propose a manual plan change, e.g. "move all study for task 3 to Tuesday" or "only mornings".
        allowed_windows: list of {"start": "YYYY-MM-DDTHH:MM", "end": "YYYY-MM-DDTHH:MM"} where these tasks may be placed.
        daily_time_window: {"from": "HH:MM", "to": "HH:MM"} for a time of day on every day (combined with allowed_windows if both).
        daily_max_minutes: optional temporary daily limit. Requires user approval."""
        raise RuntimeError("handled by the graph")

    @tool
    def propose_deadline_change(reason: str, task_id: int, new_deadline: str) -> str:
        """Propose changing a task's deadline (ISO date or datetime). The schedule is recomputed. Requires approval."""
        raise RuntimeError("handled by the graph")

    @tool
    def propose_duration_change(reason: str, task_id: int, new_estimated_minutes: int) -> str:
        """Propose changing the total required work time of a task. The schedule is recomputed. Requires approval."""
        raise RuntimeError("handled by the graph")

    @tool
    def propose_delete_task(reason: str, task_id: int) -> str:
        """Propose deleting a task and its sessions. Requires approval."""
        raise RuntimeError("handled by the graph")

    return [
        list_tasks, find_tasks, get_schedule, check_availability, get_progress_summary, get_settings, resolve_hebrew_date,
        create_task, update_task_details, log_progress, mark_task_done, update_preferences, add_weekly_rule,
        remove_weekly_rule, add_date_exception, remove_date_exception,
        propose_schedule, propose_reschedule, propose_deadline_change, propose_duration_change, propose_delete_task,
    ]

"""load_context: בונה את הקשר התור מהמסד (תאריכים, העדפות, משימות פעילות)."""

from __future__ import annotations

from daypilot.agent.dates import HEBREW_WEEKDAYS, days_table, il_weekday
from daypilot.agent.prompts import CONTEXT_TEMPLATE
from daypilot.agent.state import AgentState
from daypilot.container import AppContainer
from daypilot.jewish_calendar.calendar import day_info
from daypilot.utils.clock import to_local


def make_load_context(container: AppContainer):
    tz = container.settings.timezone

    def load_context(state: AgentState) -> dict:
        user_id = state["user_id"]
        now_local = to_local(container.clock.now(), tz)
        today = now_local.date()
        with container.unit() as svc:
            user = svc.settings.users.get(user_id)
            prefs = svc.settings.preferences(user_id)
            rows = []
            for t in svc.tasks.list(user_id):
                v = svc.tasks.view(t)
                deadline = to_local(v.deadline, tz).strftime("%Y-%m-%d %H:%M") if v.deadline else "-"
                rows.append(
                    f"{v.id} | {v.title} | {v.task_type} | {deadline} | {v.remaining_minutes if v.remaining_minutes is not None else '-'}"
                    f" | {v.scheduled_minutes}"
                )
            city = user.city.name_en if user and user.city else "Jerusalem"
        context = CONTEXT_TEMPLATE.format(
            now_local=now_local.strftime("%Y-%m-%d %H:%M"),
            weekday=HEBREW_WEEKDAYS[il_weekday(today)],
            today=today.isoformat(),
            hebrew_date=day_info(today).hebrew_date,
            buffer_hours=f"{prefs.shabbat_buffer_minutes / 60:g}",
            city=city,
            chol_hamoed=" Chol HaMoed is blocked too." if prefs.block_chol_hamoed else "",
            days_table=days_table(today),
            min_session=prefs.min_session_minutes,
            max_session=prefs.max_session_minutes,
            daily_max=prefs.daily_max_minutes,
            tasks="\n".join(rows) if rows else "(none)",
        )
        return {"context": context, "tool_rounds": 0, "last_error": None}

    return load_context

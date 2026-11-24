"""
הרצת תרחיש אחד מול האגנט האמיתי, בסביבה מבודדת.

לכל תרחיש: מסד חדש בתיקייה זמנית, שעון קבוע, מצב התחלתי לפי setup,
ואז שליחת ההודעות. אם הגרף עוצר לאישור, עונים לפי decision (ברירת מחדל: approve).
התוצאה היא תמונת מצב מלאה (תשובות, כלים, הצעות, מה נכתב למסד) שהבודקים מעריכים.
"""

from __future__ import annotations

import sys
import tempfile
from datetime import datetime, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from langchain_core.messages import AIMessage, ToolMessage  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402
from sqlalchemy import select  # noqa: E402

from daypilot.agent.runner import AgentRunner  # noqa: E402
from daypilot.config import Settings  # noqa: E402
from daypilot.container import AppContainer  # noqa: E402
from daypilot.db.models import AvailabilityException, ScheduledSession, Task  # noqa: E402
from daypilot.domain.enums import AvailabilityKind, ProposalKind, SessionStatus, TaskType  # noqa: E402
from daypilot.domain.schemas import TaskCreate, WeeklyRuleIn  # noqa: E402
from daypilot.utils.clock import FixedClock, local_datetime, to_local  # noqa: E402

TZ = "Asia/Jerusalem"
MAX_APPROVALS = 3


def _snapshot(container: AppContainer) -> dict:
    with container.unit() as svc:
        tasks = list(svc.session.scalars(select(Task)))
        titles = {t.id: t.title for t in tasks}
        sessions = [s for s in svc.session.scalars(select(ScheduledSession)) if s.status != SessionStatus.CANCELLED]
        exceptions = list(svc.session.scalars(select(AvailabilityException)))
        return {
            "tasks": [
                {
                    "id": t.id, "title": t.title, "type": t.task_type, "status": t.status, "importance": t.importance,
                    "deadline": to_local(t.deadline, TZ).isoformat() if t.deadline else None,
                    "estimated_minutes": t.estimated_minutes, "remaining_minutes": t.remaining_minutes,
                    "recurrence_rule": t.recurrence_rule,
                }
                for t in tasks
            ],
            "sessions": [
                {
                    "task_id": s.task_id, "task_title": titles.get(s.task_id, ""), "status": s.status,
                    "start": to_local(s.start, TZ).isoformat(), "end": to_local(s.end, TZ).isoformat(),
                }
                for s in sorted(sessions, key=lambda x: x.start)
            ],
            "exceptions": [{"day": e.day.isoformat(), "kind": e.kind} for e in exceptions],
        }


def _setup(container: AppContainer, user_id: int, setup: dict, today) -> None:
    with container.unit() as svc:
        for r in setup.get("rules", []):
            svc.settings.add_rule(user_id, WeeklyRuleIn(
                weekday=r["weekday"], start_time=time.fromisoformat(r["start"]), end_time=time.fromisoformat(r["end"]),
                kind=AvailabilityKind(r["kind"]), label=r.get("label", "")))
        for t in setup.get("tasks", []):
            deadline = local_datetime(today + timedelta(days=t["deadline_days"]), time(9), TZ) if "deadline_days" in t else None
            svc.tasks.create(user_id, TaskCreate(
                title=t["title"], task_type=TaskType(t["type"]), deadline=deadline,
                estimated_minutes=t.get("minutes"), importance=t.get("importance", 3)))
    if setup.get("schedule"):
        with container.unit() as svc:
            proposal = svc.schedule.propose(user_id, ProposalKind.SCHEDULE, "setup")
            svc.schedule.apply_proposal(user_id, proposal, "setup")


def run_scenario(inputs: dict, llm) -> dict:
    now = datetime.fromisoformat(inputs["now"])
    with tempfile.TemporaryDirectory(prefix="daypilot-eval-", ignore_cleanup_errors=True) as tmp:
        settings = Settings(data_dir=Path(tmp))  # מפתחות ו-Tracing נקראים מ-.env
        container = AppContainer(settings=settings, clock=FixedClock(now))
        user_id = container.default_user_id()
        _setup(container, user_id, inputs.get("setup") or {}, now.date())
        before = _snapshot(container)

        runner = AgentRunner(container, llm=llm, checkpointer=InMemorySaver())
        thread = "eval"
        replies: list[str] = []
        approvals: list[dict] = []
        written_before_approval = False
        reference = before  # המצב המאושר האחרון; כל שינוי משמעותי לפני אישור הוא הפרה
        error = None
        try:
            for text in inputs["messages"]:
                result = runner.send(user_id, thread, text)
                rounds = 0
                while result.approval is not None and rounds < MAX_APPROVALS:
                    rounds += 1
                    # שינויים שמותר לעשות אוטומטית (משימה חדשה, התקדמות) לא נחשבים הפרה
                    written_before_approval |= _significant_change(reference, _snapshot(container))
                    proposal = result.approval["proposal"]
                    approvals.append({
                        "kind": proposal["kind"], "feasible": proposal["feasible"],
                        "conflict_kinds": sorted({c["kind"] for c in proposal["conflicts"]}),
                        "add_sessions": len(proposal["add_sessions"]), "remove_sessions": len(proposal["remove_session_ids"]),
                        "display": result.approval["display"],
                    })
                    result = runner.resume(thread, inputs.get("decision") or "approve")
                    reference = _snapshot(container)
                if result.reply:
                    replies.append(result.reply)
        except Exception as exc:  # תרחיש שנכשל נרשם כתוצאה, לא מפיל את הניסוי
            error = f"{type(exc).__name__}: {exc}"[:500]

        state = runner.graph.get_state(runner._config(thread)).values
        tool_calls = [
            {"name": c["name"], "args": c.get("args", {})}
            for m in state.get("messages", []) if isinstance(m, AIMessage) for c in (m.tool_calls or [])
        ]
        tool_results = [str(m.content) for m in state.get("messages", []) if isinstance(m, ToolMessage)]
        after = _snapshot(container)
        container.engine.dispose()
        if hasattr(runner.checkpointer, "conn"):
            runner.checkpointer.conn.close()

    return {
        "final_reply": replies[-1] if replies else "",
        "replies": replies,
        "tool_calls": tool_calls,
        "tool_results": tool_results,
        "approvals": approvals,
        "written_before_approval": written_before_approval,
        "before": before,
        "after": after,
        "error": error,
    }


def _significant_change(before: dict, now: dict) -> bool:
    """שינוי שדורש אישור: מפגשים שונו, משימה נמחקה, מועד או משך השתנו."""
    if now["sessions"] != before["sessions"]:
        return True
    old = {t["id"]: t for t in before["tasks"]}
    current = {t["id"]: t for t in now["tasks"]}
    if set(old) - set(current):
        return True
    for tid, t in old.items():
        c = current.get(tid)
        if c and (c["deadline"] != t["deadline"] or c["estimated_minutes"] != t["estimated_minutes"]):
            return True
    return False

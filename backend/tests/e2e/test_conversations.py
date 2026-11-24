"""
תרחישי שיחה מלאים: כמה תורות, כלים, אישורים ומקרי קצה.
המודל מזויף, אבל כל השאר אמיתי: מסד, מנוע תכנון, לוח עברי ו-Checkpointer.
"""

from __future__ import annotations

import json
from datetime import time, timedelta

import pytest
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select

from daypilot.agent.runner import AgentRunner
from daypilot.config import Settings
from daypilot.container import AppContainer
from daypilot.db.models import ScheduledSession, Task
from daypilot.domain.enums import SessionStatus, TaskStatus
from daypilot.domain.schemas import TaskDetailsUpdate
from daypilot.services.errors import ValidationError
from daypilot.utils.clock import to_local
from tests.conftest import START_DAY, TZ, L
from tests.fakes import ScriptedModel, call, say


@pytest.fixture
def container(tmp_path, clock):
    return AppContainer(settings=Settings(_env_file=None, data_dir=tmp_path), clock=clock)


@pytest.fixture
def user_id(container):
    return container.default_user_id()


def runner_with(container, script):
    model = ScriptedModel(script=list(script))
    return AgentRunner(container, llm=model, checkpointer=InMemorySaver()), model


def last_tool_results(model) -> list[dict]:
    return [json.loads(m.content) for m in model.seen[-1] if isinstance(m, ToolMessage)]


def sessions(container, status=SessionStatus.PLANNED):
    with container.unit() as svc:
        return [s for s in svc.session.scalars(select(ScheduledSession)) if s.status == status]


def day(n: int) -> str:
    return (START_DAY + timedelta(days=n)).isoformat()


# ---------------------------------------------------------------- תרחישים מלאים


def test_two_tasks_that_do_not_fit_show_conflict_and_alternatives(container, user_id):
    runner, model = runner_with(container, [
        call("create_task", title="מבחן", task_type="scheduled", deadline=day(2), estimated_minutes=600),
        call("create_task", title="עבודה", task_type="scheduled", deadline=day(2), estimated_minutes=480),
        call("propose_schedule", reason="שיבוץ", task_ids=[1, 2]),
        say("אין מספיק זמן לשתיהן. אישרתי את מה שאפשר."),
    ])
    first = runner.send(user_id, "t1", "מבחן ועבודה ביום שלישי")
    assert first.approval is not None
    proposal = first.approval["proposal"]
    assert proposal["feasible"] is False
    assert any(c["kind"] == "capacity" for c in proposal["conflicts"])
    assert proposal["alternatives"], "alternatives should be computed, not invented"
    assert "אין מספיק זמן" in first.approval["display"]

    runner.resume("t1", "approve")  # המשתמשת מאשרת שיבוץ חלקי
    total = sum((s.end - s.start).total_seconds() / 60 for s in sessions(container))
    assert 0 < total < 600 + 480


def test_proposal_goes_stale_while_waiting_and_is_recomputed(container, user_id):
    runner, model = runner_with(container, [
        call("create_task", title="מבחן", task_type="scheduled", deadline=day(4), estimated_minutes=240),
        call("propose_schedule", reason="s", task_ids=[1]),
        call("propose_schedule", reason="מחושב מחדש", task_ids=[1]),  # המודל מחשב שוב אחרי stale
        say("שובץ לפי הנתונים המעודכנים."),
    ])
    runner.send(user_id, "t1", "תשבץ מבחן")
    with container.unit() as svc:  # שינוי בזמן ההמתנה (למשל מהממשק)
        svc.tasks.update_details(user_id, 1, TaskDetailsUpdate(importance=5))

    second = runner.resume("t1", "approve")
    assert last_tool_results(model)[-1]["status"] == "stale"
    assert second.approval is not None, "a fresh proposal should be waiting"
    assert sessions(container) == []

    final = runner.resume("t1", "approve")
    assert final.reply == "שובץ לפי הנתונים המעודכנים."
    assert sessions(container)


def test_weekly_quiz_with_prep_through_chat(container, user_id):
    runner, model = runner_with(container, [
        call("create_task", title="בוחן", task_type="recurring", recurrence_rule="FREQ=WEEKLY;BYDAY=WE",
             occurrence_time="10:00", occurrence_minutes=60, prep_minutes=60),
        call("propose_schedule", reason="הכנה לבוחן"),
        say("שיבצתי שעת הכנה לפני כל בוחן."),
    ])
    runner.send(user_id, "t1", "יש לי בוחן בכל יום רביעי ב-10, אני צריכה שעה הכנה")
    runner.resume("t1", "approve")
    wednesday = START_DAY + timedelta(days=3)
    prep = [s for s in sessions(container) if s.occurrence_date == wednesday]
    assert prep and all(s.end <= L(wednesday, 10) for s in prep)


def test_progress_and_completion_through_chat(container, user_id):
    runner, model = runner_with(container, [
        call("create_task", title="פרויקט", task_type="scheduled", deadline=day(5), estimated_minutes=180),
        call("propose_schedule", reason="s", task_ids=[1]),
        say("שובץ."),
        call("log_progress", task_id=1, minutes=60, note="פרק 1"),
        say("רשמתי שעה."),
        call("mark_task_done", task_id=1),
        say("כל הכבוד!"),
    ])
    runner.send(user_id, "t1", "פרויקט, 3 שעות")
    runner.resume("t1", "approve")
    runner.send(user_id, "t1", "עבדתי שעה על הפרויקט")
    with container.unit() as svc:
        assert svc.tasks.get(user_id, 1).remaining_minutes == 120
    runner.send(user_id, "t1", "סיימתי את הפרויקט")
    with container.unit() as svc:
        assert svc.tasks.get(user_id, 1).status == TaskStatus.DONE
    assert sessions(container) == []  # מפגשים עתידיים שוחררו
    assert sessions(container, SessionStatus.CANCELLED)


def test_conversation_keeps_context_between_turns(container, user_id):
    runner, model = runner_with(container, [say("בשמחה."), say("כן, זוכרת.")])
    runner.send(user_id, "t1", "קוראים לי רחל")
    runner.send(user_id, "t1", "את זוכרת איך קוראים לי?")
    humans = [m.content for m in model.seen[-1] if isinstance(m, HumanMessage)]
    assert humans == ["קוראים לי רחל", "את זוכרת איך קוראים לי?"]


def test_settings_change_affects_availability(container, user_id):
    runner, model = runner_with(container, [
        call("add_weekly_rule", weekday=0, start_time="09:00", end_time="14:00", kind="class", label="לימודים"),
        say("עדכנתי."),
        call("check_availability", start_date=START_DAY.isoformat(), end_date=START_DAY.isoformat()),
        say("יש לך זמן פנוי אחר הצהריים."),
    ])
    runner.send(user_id, "t1", "ביום ראשון אני לומדת 9 עד 2")
    runner.send(user_id, "t1", "מתי אני פנויה היום?")
    windows = last_tool_results(model)[-1]["days"][START_DAY.isoformat()]["windows"]
    assert windows and all(not ("09:00" <= w["start"][11:16] < "14:00") for w in windows)


def test_hebrew_date_tool(container, user_id):
    runner, model = runner_with(container, [call("resolve_hebrew_date", day=15, month="שבט"), say("ט\"ו בשבט.")])
    runner.send(user_id, "t1", "מתי ט\"ו בשבט?")
    result = last_tool_results(model)[-1]
    assert result["date"] > START_DAY.isoformat()


def test_date_only_deadline_is_recorded_as_assumption(container, user_id):
    runner, model = runner_with(container, [
        call("create_task", title="הגשה", task_type="scheduled", deadline=day(3), estimated_minutes=120),
        say("הוספתי."),
    ])
    runner.send(user_id, "t1", "הגשה ביום רביעי")
    task = last_tool_results(model)[-1]["task"]
    assert any("date only" in a for a in task["assumptions"])
    assert to_local_deadline(container) == L(START_DAY + timedelta(days=3), 0)


def to_local_deadline(container):
    with container.unit() as svc:
        task = svc.session.scalars(select(Task)).one()
        return to_local(task.deadline, TZ)


# ---------------------------------------------------------------- מקרי קצה


def test_proposal_mixed_with_other_tool_runs_proposal_only(container, user_id):
    runner, model = runner_with(container, [
        call("create_task", title="מבחן", task_type="scheduled", deadline=day(3), estimated_minutes=120),
        say("נוצר."),
    ])
    runner.send(user_id, "t1", "מבחן")
    from langchain_core.messages import AIMessage

    mixed = AIMessage(content="", tool_calls=[
        {"name": "list_tasks", "args": {}, "id": "a", "type": "tool_call"},
        {"name": "propose_schedule", "args": {"reason": "s", "task_ids": [1]}, "id": "b", "type": "tool_call"},
    ])
    model.script.extend([mixed])
    result = runner.send(user_id, "t1", "תשבץ")
    assert result.approval is not None
    skipped = [json.loads(m.content) for m in runner.graph.get_state(runner._config("t1")).values["messages"]
               if isinstance(m, ToolMessage)][-1]
    assert skipped["ok"] is False and "alone" in skipped["error"]


def test_invalid_reschedule_window_is_reported(container, user_id):
    runner, model = runner_with(container, [
        call("create_task", title="מבחן", task_type="scheduled", deadline=day(4), estimated_minutes=120),
        call("propose_reschedule", reason="r", task_ids=[1],
             allowed_windows=[{"start": f"{day(2)}T18:00", "end": f"{day(2)}T10:00"}]),
        say("החלון לא תקין, מה התכוונת?"),
    ])
    result = runner.send(user_id, "t1", "רק ביום שלישי")
    assert result.approval is None
    assert "after it starts" in last_tool_results(model)[-1]["error"]


def test_runner_input_validation(container, user_id):
    runner, _ = runner_with(container, [])
    with pytest.raises(ValidationError):
        runner.send(user_id, "t1", "   ")
    with pytest.raises(ValidationError):
        runner.send(user_id, "t1", "א" * 5000)
    with pytest.raises(ValidationError):
        runner.resume("t1", "approve")  # אין מה לאשר
    with pytest.raises(ValidationError):
        runner.resume("t1", "maybe")


def test_locked_and_done_sessions_are_not_moved(container, user_id, clock):
    runner, _ = runner_with(container, [
        call("create_task", title="מבחן", task_type="scheduled", deadline=day(5), estimated_minutes=240),
        call("propose_schedule", reason="s", task_ids=[1]),
        say("שובץ."),
        call("add_date_exception", day=day(1), kind="blocked"),
        call("propose_schedule", reason="תכנון מחדש"),
        say("עדכנתי."),
    ])
    runner.send(user_id, "t1", "מבחן")
    runner.resume("t1", "approve")
    with container.unit() as svc:
        first = sorted(svc.session.scalars(select(ScheduledSession)), key=lambda s: s.start)[0]
        first.locked = True
        locked_id, locked_start = first.id, first.start

    runner.send(user_id, "t1", "מחר אני לא פנויה בכלל")
    if runner.pending("t1"):
        runner.resume("t1", "approve")
    with container.unit() as svc:
        still = svc.session.get(ScheduledSession, locked_id)
        assert still is not None and still.start == locked_start
        movable = [s for s in svc.session.scalars(select(ScheduledSession)) if not s.locked]
    blocked_day = START_DAY + timedelta(days=1)
    assert all(to_local(s.start, TZ).date() != blocked_day for s in movable)


# ---------------------------------------------------------------- שיפורי v2


def test_daily_time_window_and_session_days_in_result(container, user_id):
    runner, model = runner_with(container, [
        call("create_task", title="מבחן", task_type="scheduled", deadline=day(4), estimated_minutes=480),
        call("propose_schedule", reason="רק בערבים", task_ids=[1], daily_time_window={"from": "17:00", "to": "22:00"}),
        say("שובץ בערבים."),
    ])
    runner.send(user_id, "t1", "מבחן ביום חמישי, 8 שעות, רק בערבים")
    runner.resume("t1", "approve")
    planned = sessions(container)
    assert planned
    assert all(time(17) <= to_local(s.start, TZ).time() and to_local(s.end, TZ).time() <= time(22) for s in planned)

    applied = last_tool_results(model)[-1]
    by_day = applied["summary"]["new_sessions_by_day"]
    real_days = sorted({to_local(s.start, TZ).date().isoformat() for s in planned})
    assert [d["date"] for d in by_day] == real_days
    assert applied["summary"]["last_session_date"] == real_days[-1]


def test_bad_daily_time_window_is_reported(container, user_id):
    runner, model = runner_with(container, [
        call("create_task", title="מבחן", task_type="scheduled", deadline=day(4), estimated_minutes=120),
        call("propose_schedule", reason="r", task_ids=[1], daily_time_window={"from": "22:00", "to": "17:00"}),
        say("השעות לא תקינות."),
    ])
    result = runner.send(user_id, "t1", "רק בערבים")
    assert result.approval is None
    assert "after" in last_tool_results(model)[-1]["error"]

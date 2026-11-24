"""
בדיקות לגרף LangGraph: כל המסלולים, interrupt/resume, ושמירת מצב אחרי "הפעלה מחדש".
המודל מזויף (ScriptedModel), כך שאין קריאות ל-OpenAI ואין עלות.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from langchain_core.messages import ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import func, select

from daypilot.agent.graph import make_sqlite_checkpointer
from daypilot.agent.runner import AgentRunner, PendingApprovalError
from daypilot.config import Settings
from daypilot.container import AppContainer
from daypilot.db.models import Message, Proposal, ScheduledSession, Task
from daypilot.domain.enums import TaskType
from daypilot.domain.schemas import TaskCreate
from tests.conftest import START_DAY, L
from tests.fakes import ScriptedModel, call, say

DEADLINE = (START_DAY + timedelta(days=5)).isoformat()


@pytest.fixture
def container(tmp_path, clock):
    settings = Settings(_env_file=None, data_dir=tmp_path, openai_api_key=None)
    return AppContainer(settings=settings, clock=clock)


@pytest.fixture
def user_id(container):
    return container.default_user_id()


def make_runner(container, script, checkpointer=None, **model_kwargs):
    model = ScriptedModel(script=list(script), **model_kwargs)
    return AgentRunner(container, llm=model, checkpointer=checkpointer or InMemorySaver()), model


def count(container, model_cls) -> int:
    with container.unit() as svc:
        return svc.session.scalar(select(func.count()).select_from(model_cls))


def tool_messages(model: ScriptedModel) -> list[dict]:
    return [json.loads(m.content) for m in model.seen[-1] if isinstance(m, ToolMessage)]


def create_exam(container, user_id):
    with container.unit() as svc:
        task = svc.tasks.create(
            user_id,
            TaskCreate(title="מבחן", task_type=TaskType.SCHEDULED, deadline=L(START_DAY + timedelta(days=5), 9),
                       estimated_minutes=240),
        )
        return task.id


# ---------------------------------------------------------------- מסלולים בסיסיים


def test_plain_answer_is_saved_to_history(container, user_id):
    runner, model = make_runner(container, [say("שלום! במה אפשר לעזור?")])
    result = runner.send(user_id, "t1", "היי")
    assert result.reply == "שלום! במה אפשר לעזור?"
    assert result.approval is None
    assert count(container, Message) == 2  # הודעת המשתמשת ותשובת האגנט
    system = model.seen[0][0].content
    assert "Upcoming days" in system and START_DAY.isoformat() in system  # הקשר התאריכים נכנס


def test_create_task_runs_automatically(container, user_id):
    runner, model = make_runner(
        container,
        [call("create_task", title="פרויקט", task_type="scheduled", deadline=DEADLINE, estimated_minutes=600),
         say("הוספתי.")],
    )
    result = runner.send(user_id, "t1", "יש לי פרויקט")
    assert result.reply == "הוספתי."
    assert count(container, Task) == 1
    assert tool_messages(model)[0]["ok"] is True


def test_tool_error_goes_back_to_model(container, user_id):
    runner, model = make_runner(
        container,
        [call("create_task", title="מבחן", task_type="scheduled"),  # חסרים מועד ומשך
         say("מתי המבחן וכמה שעות צריך?")],
    )
    result = runner.send(user_id, "t1", "יש לי מבחן")
    assert result.reply.startswith("מתי")
    assert tool_messages(model)[0]["ok"] is False
    assert count(container, Task) == 0


# ---------------------------------------------------------------- Human-in-the-Loop


def test_schedule_waits_for_approval_and_applies(container, user_id):
    task_id = create_exam(container, user_id)
    runner, model = make_runner(container, [call("propose_schedule", reason="שיבוץ", task_ids=[task_id]), say("שובץ.")])

    first = runner.send(user_id, "t1", "תשבץ לי את המבחן")
    assert first.reply is None and first.approval is not None
    assert first.approval["type"] == "proposal_approval"
    assert "מפגשים חדשים" in first.approval["display"]
    assert count(container, ScheduledSession) == 0  # כלום לא נכתב לפני אישור
    assert runner.pending("t1") is not None

    second = runner.resume("t1", "approve")
    assert second.reply == "שובץ."
    assert count(container, ScheduledSession) > 0
    applied = tool_messages(model)[-1]
    assert applied["applied"] is True
    with container.unit() as svc:
        assert svc.session.scalars(select(Proposal)).one().status == "approved"


def test_reject_writes_nothing(container, user_id):
    task_id = create_exam(container, user_id)
    runner, model = make_runner(container, [call("propose_schedule", reason="s", task_ids=[task_id]), say("בסדר, לא שיניתי.")])
    runner.send(user_id, "t1", "תשבץ")
    result = runner.resume("t1", "reject", "לא עכשיו")
    assert result.reply == "בסדר, לא שיניתי."
    assert count(container, ScheduledSession) == 0
    feedback = tool_messages(model)[-1]
    assert feedback["status"] == "rejected_by_user" and feedback["feedback"] == "לא עכשיו"


def test_revise_loops_back_to_a_new_proposal(container, user_id):
    task_id = create_exam(container, user_id)
    tuesday = (START_DAY + timedelta(days=2)).isoformat()
    runner, model = make_runner(
        container,
        [
            call("propose_schedule", reason="s", task_ids=[task_id]),
            call("propose_reschedule", reason="רק שלישי", task_ids=[task_id],
                 allowed_windows=[{"start": f"{tuesday}T00:00", "end": tuesday}]),
            say("הכל ביום שלישי."),
        ],
    )
    runner.send(user_id, "t1", "תשבץ")
    second = runner.resume("t1", "revise", "הכל ביום שלישי")
    assert second.approval is not None, "expected a second proposal"
    assert tool_messages(model)[-1]["status"] == "user_requested_changes"
    final = runner.resume("t1", "approve")
    assert final.reply == "הכל ביום שלישי."
    with container.unit() as svc:
        rows = list(svc.session.scalars(select(ScheduledSession)))
    assert rows and all(r.start.astimezone(L(START_DAY, 0).tzinfo).date().isoformat() == tuesday for r in rows)


def test_delete_requires_approval(container, user_id):
    task_id = create_exam(container, user_id)
    runner, _ = make_runner(container, [call("propose_delete_task", reason="r", task_id=task_id), say("נמחק.")])
    first = runner.send(user_id, "t1", "תמחק את המבחן")
    assert first.approval is not None
    assert count(container, Task) == 1
    runner.resume("t1", "approve")
    assert count(container, Task) == 0


def test_cannot_send_while_waiting_for_approval(container, user_id):
    task_id = create_exam(container, user_id)
    runner, _ = make_runner(container, [call("propose_schedule", reason="s", task_ids=[task_id])])
    runner.send(user_id, "t1", "תשבץ")
    with pytest.raises(PendingApprovalError):
        runner.send(user_id, "t1", "עוד משהו")


def test_approval_survives_restart(container, user_id, tmp_path):
    task_id = create_exam(container, user_id)
    path = tmp_path / "checkpoints.db"
    runner, _ = make_runner(container, [call("propose_schedule", reason="s", task_ids=[task_id])],
                            checkpointer=make_sqlite_checkpointer(path))
    runner.send(user_id, "t1", "תשבץ")
    del runner  # "סגירת" התוכנית

    revived, _ = make_runner(container, [say("שובץ אחרי הפעלה מחדש.")], checkpointer=make_sqlite_checkpointer(path))
    assert revived.pending("t1") is not None
    result = revived.resume("t1", "approve")
    assert result.reply == "שובץ אחרי הפעלה מחדש."
    assert count(container, ScheduledSession) > 0


def test_invalid_proposal_goes_back_to_model(container, user_id):
    runner, model = make_runner(container, [call("propose_delete_task", reason="r", task_id=999), say("לא מצאתי משימה כזו.")])
    result = runner.send(user_id, "t1", "תמחק")
    assert result.approval is None
    assert result.reply == "לא מצאתי משימה כזו."
    assert tool_messages(model)[-1]["ok"] is False


# ---------------------------------------------------------------- שגיאות והגנות


def test_api_error_becomes_friendly_reply(container, user_id):
    class RateLimitError(Exception):
        pass

    runner, _ = make_runner(container, [RateLimitError("insufficient_quota")])
    result = runner.send(user_id, "t1", "היי")
    assert "קרדיט" in result.reply


def test_tool_loop_is_capped(container, user_id):
    runner, _ = make_runner(container, [call("list_tasks")], repeat_last=True)
    result = runner.send(user_id, "t1", "תבדוק שוב ושוב")
    assert "לא הצלחתי" in result.reply


def test_delete_history_keeps_tasks(container, user_id):
    runner, _ = make_runner(
        container,
        [call("create_task", title="מחברת", task_type="open"), say("הוספתי.")],
    )
    runner.send(user_id, "t1", "אני צריכה לקנות מחברת")
    runner.delete_thread(user_id, "t1")
    assert count(container, Message) == 0
    assert count(container, Task) == 1
    assert runner.graph.get_state(runner._config("t1")).values == {}

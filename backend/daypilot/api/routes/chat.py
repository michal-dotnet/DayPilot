"""
צ'אט עם האגנט.

הממשק שולח הודעה, ומקבל תשובה או הצעה שממתינה לאישור.
ההחלטה נשלחת לנתיב decision, שקורא ל-Command(resume=...) בגרף (כמו input() בטרמינל אצל המורה).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from daypilot.agent.runner import AgentRunner, TurnResult
from daypilot.api.deps import AppState, state
from daypilot.services.errors import NotFoundError

router = APIRouter(prefix="/api/chat")


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class DecisionIn(BaseModel):
    action: str = Field(pattern="^(approve|reject|revise)$")
    feedback: str = Field(default="", max_length=1000)


def _turn(result: TurnResult) -> dict:
    return {"thread_id": result.thread_id, "reply": result.reply, "approval": result.approval}


@router.get("/threads")
def threads(app: AppState = Depends(state)) -> list[dict]:
    with app.container.unit() as svc:
        return [
            {"id": c.id, "title": c.title, "updated_at": c.updated_at}
            for c in svc.conversations.list(app.user_id)
        ]


@router.post("/threads")
def new_thread() -> dict:
    return {"id": AgentRunner.new_thread_id()}


@router.get("/threads/{thread_id}")
def thread(thread_id: str, app: AppState = Depends(state)) -> dict:
    with app.container.unit() as svc:
        try:
            messages = [
                {"role": m.role, "content": m.content, "created_at": m.created_at}
                for m in svc.conversations.messages(app.user_id, thread_id)
            ]
        except NotFoundError:
            messages = []
    pending = app.runner().pending(thread_id) if messages else None
    return {"id": thread_id, "messages": messages, "approval": pending}


@router.post("/threads/{thread_id}/messages")
def send(thread_id: str, data: MessageIn, app: AppState = Depends(state)) -> dict:
    runner = app.runner()
    with app.agent_lock:
        return _turn(runner.send(app.user_id, thread_id, data.text))


@router.post("/threads/{thread_id}/decision")
def decide(thread_id: str, data: DecisionIn, app: AppState = Depends(state)) -> dict:
    runner = app.runner()
    with app.agent_lock:
        return _turn(runner.resume(thread_id, data.action, data.feedback))


@router.delete("/threads/{thread_id}")
def delete(thread_id: str, app: AppState = Depends(state)) -> dict:
    """מחיקת היסטוריה: גם מהמסד וגם מה-Checkpointer. המשימות נשארות."""
    with app.agent_lock:
        app.runner().delete_thread(app.user_id, thread_id)
    return {"ok": True}

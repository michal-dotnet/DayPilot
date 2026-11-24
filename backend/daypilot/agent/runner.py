"""
הפעלת האגנט: שליחת הודעה, המשך אחרי אישור, ושליפת מצב.

ה-CLI, ה-API והניסויים משתמשים באותו Runner, כמו שבפרויקט המורה
גם הטרמינל וגם Streamlit שולחים Command(resume=...) לאותו גרף.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command

from daypilot.agent.graph import build_graph, make_sqlite_checkpointer
from daypilot.agent.llm import build_llm
from daypilot.agent.nodes.approval import APPROVAL_ACTIONS
from daypilot.agent.nodes.turn import message_text
from daypilot.agent.prompts import PROMPT_VERSION
from daypilot.container import AppContainer
from daypilot.services.errors import ValidationError

MAX_USER_MESSAGE = 4000


class PendingApprovalError(Exception):
    """יש הצעה שממתינה להחלטה בשיחה הזו. קודם מחליטים, אחר כך ממשיכים."""


@dataclass
class TurnResult:
    thread_id: str
    reply: str | None  # תשובת האגנט, אם התור הסתיים
    approval: dict | None  # הצעה שממתינה לאישור, אם הגרף עצר


class AgentRunner:
    def __init__(
        self,
        container: AppContainer,
        llm: BaseChatModel | None = None,
        checkpointer: BaseCheckpointSaver | None = None,
    ):
        self.container = container
        self.checkpointer = checkpointer or make_sqlite_checkpointer(container.settings.checkpoint_db_path)
        self.graph = build_graph(container, llm or build_llm(container.settings), self.checkpointer)

    @staticmethod
    def new_thread_id() -> str:
        return f"t-{uuid.uuid4().hex[:12]}"

    def _config(self, thread_id: str) -> dict:
        return {
            "configurable": {"thread_id": thread_id},
            "run_name": "daypilot-turn",
            "tags": [f"prompt:{PROMPT_VERSION}", f"model:{self.container.settings.model_name}"],
            "metadata": {"thread_id": thread_id, "prompt_version": PROMPT_VERSION},
            "recursion_limit": 60,
        }

    def pending(self, thread_id: str) -> dict | None:
        snapshot = self.graph.get_state(self._config(thread_id))
        if snapshot and snapshot.interrupts:
            return snapshot.interrupts[0].value
        return None

    def send(self, user_id: int, thread_id: str, text: str) -> TurnResult:
        text = (text or "").strip()
        if not text:
            raise ValidationError("empty message")
        if len(text) > MAX_USER_MESSAGE:
            raise ValidationError(f"message too long (max {MAX_USER_MESSAGE} characters)")
        if self.pending(thread_id):
            raise PendingApprovalError("a proposal is waiting for a decision in this conversation")
        with self.container.unit() as svc:
            svc.conversations.add_message(user_id, thread_id, "user", text)
        result = self.graph.invoke(
            {"messages": [HumanMessage(content=text)], "user_id": user_id, "thread_id": thread_id},
            self._config(thread_id),
        )
        return self._result(thread_id, result)

    def resume(self, thread_id: str, action: str, feedback: str = "") -> TurnResult:
        if action not in APPROVAL_ACTIONS:
            raise ValidationError(f"action must be one of {APPROVAL_ACTIONS}")
        if not self.pending(thread_id):
            raise ValidationError("nothing is waiting for approval in this conversation")
        result = self.graph.invoke(
            Command(resume={"action": action, "feedback": feedback}), self._config(thread_id)
        )
        return self._result(thread_id, result)

    def delete_thread(self, user_id: int, thread_id: str) -> None:
        """מחיקת היסטוריה: גם מהמסד וגם מה-Checkpointer. משימות לא נמחקות."""
        self.checkpointer.delete_thread(thread_id)
        with self.container.unit() as svc:
            svc.conversations.delete(user_id, thread_id)

    def _result(self, thread_id: str, result: dict) -> TurnResult:
        if result.get("__interrupt__"):
            return TurnResult(thread_id, None, result["__interrupt__"][0].value)
        messages = result.get("messages") or []
        last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
        return TurnResult(thread_id, message_text(last_ai) if last_ai else None, None)

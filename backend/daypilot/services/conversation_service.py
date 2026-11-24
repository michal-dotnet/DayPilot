"""
היסטוריית שיחות במסד.

ה-Checkpointer שומר את מצב הגרף (כולל הודעות כלים פנימיות).
כאן נשמרות רק ההודעות שהמשתמשת רואה: שלה ושל האגנט, לתצוגה ולמחיקה.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot.db.models import Conversation, Message
from daypilot.services.errors import NotFoundError
from daypilot.utils.clock import Clock


class ConversationService:
    def __init__(self, session: Session, clock: Clock):
        self.s = session
        self.clock = clock

    def ensure(self, user_id: int, thread_id: str, title: str = "") -> Conversation:
        conv = self.s.get(Conversation, thread_id)
        if conv is None:
            now = self.clock.now()
            conv = Conversation(id=thread_id, user_id=user_id, title=title[:200], created_at=now, updated_at=now)
            self.s.add(conv)
            self.s.flush()
        return conv

    def add_message(self, user_id: int, thread_id: str, role: str, content: str) -> Message:
        conv = self.ensure(user_id, thread_id, title=content if role == "user" else "")
        if not conv.title and role == "user":
            conv.title = content[:200]
        now = self.clock.now()
        msg = Message(conversation_id=conv.id, role=role, content=content, created_at=now)
        self.s.add(msg)
        conv.updated_at = now
        self.s.flush()
        return msg

    def list(self, user_id: int) -> list[Conversation]:
        return list(
            self.s.scalars(
                select(Conversation).where(Conversation.user_id == user_id).order_by(Conversation.updated_at.desc())
            )
        )

    def messages(self, user_id: int, thread_id: str) -> list[Message]:
        conv = self.s.get(Conversation, thread_id)
        if conv is None or conv.user_id != user_id:
            raise NotFoundError("conversation not found", thread_id=thread_id)
        return list(conv.messages)

    def delete(self, user_id: int, thread_id: str) -> bool:
        conv = self.s.get(Conversation, thread_id)
        if conv is None or conv.user_id != user_id:
            return False
        self.s.delete(conv)
        self.s.flush()
        return True

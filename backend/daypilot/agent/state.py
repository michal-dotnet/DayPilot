"""
ה-State של הגרף.

לפי ההחלטה במסמך: ה-State לא מחזיק עותקים של משימות.
הוא מחזיק הודעות, מזהה משתמשת, והצעה שממתינה לאישור. נתונים נקראים תמיד מהמסד.
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    user_id: int
    thread_id: str
    context: str  # הקשר התור: תאריך, טבלת ימים, משימות פעילות (נבנה מחדש בכל תור)
    tool_rounds: int  # כמה סבבי כלים היו בתור הנוכחי (הגנה מלולאה אינסופית)
    pending_proposal: dict | None  # PlanProposal במצב JSON, ממתין לאישור
    proposal_call_id: str | None  # מזהה קריאת הכלי שיצרה את ההצעה
    last_error: str | None

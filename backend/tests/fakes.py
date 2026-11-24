"""
מודל מזויף לבדיקות הגרף, בלי OpenAI ובלי עלות.

מחזיר תשובות לפי תסריט, כולל קריאות לכלים. כמו FakeListChatModel בפרויקט המורה,
אבל תומך גם ב-bind_tools ובקריאות כלים.
"""

from __future__ import annotations

import itertools
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

_ids = itertools.count(1)


def call(name: str, **args) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call_{next(_ids)}", "type": "tool_call"}])


def say(text: str) -> AIMessage:
    return AIMessage(content=text)


class ScriptedModel(BaseChatModel):
    script: list[Any] = Field(default_factory=list)  # AIMessage, Exception, או פונקציה(messages) -> AIMessage
    seen: list[list[BaseMessage]] = Field(default_factory=list)
    repeat_last: bool = False

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.seen.append(list(messages))
        if not self.script:
            raise AssertionError("ScriptedModel ran out of responses")
        item = self.script[0] if self.repeat_last and len(self.script) == 1 else self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        if callable(item):
            item = item(messages)
        if isinstance(item, AIMessage) and item.tool_calls:
            # מזהה חדש בכל שימוש, כמו מודל אמיתי
            item = AIMessage(
                content=item.content,
                tool_calls=[{**c, "id": f"call_{next(_ids)}"} for c in item.tool_calls],
            )
        return ChatResult(generations=[ChatGeneration(message=item)])

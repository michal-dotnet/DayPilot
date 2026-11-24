"""save_turn: שומר את תשובת האגנט בהיסטוריית השיחות במסד."""

from __future__ import annotations

from langchain_core.messages import AIMessage

from daypilot.agent.state import AgentState
from daypilot.container import AppContainer


def message_text(message) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    parts = [p.get("text", "") for p in content if isinstance(p, dict)]
    return "".join(parts)


def make_save_turn(container: AppContainer):
    def save_turn(state: AgentState) -> dict:
        last = state["messages"][-1]
        thread_id = state.get("thread_id")
        if isinstance(last, AIMessage) and thread_id:
            text = message_text(last).strip()
            if text:
                with container.unit() as svc:
                    svc.conversations.add_message(state["user_id"], thread_id, "assistant", text)
        return {}

    return save_turn

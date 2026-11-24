"""
agent: קריאה למודל עם הכלים, וניתוב לפי התשובה.

שגיאות API לא מפילות את הגרף: הן הופכות לתשובה ברורה למשתמשת, והתור מסתיים.
"""

from __future__ import annotations

import logging

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage

from daypilot.agent.prompts import SYSTEM_PROMPT
from daypilot.agent.state import AgentState
from daypilot.agent.tools.registry import PROPOSAL_TOOL_NAMES

log = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 8
MAX_HISTORY_MESSAGES = 40


def trim_history(messages: list[AnyMessage], limit: int = MAX_HISTORY_MESSAGES) -> list[AnyMessage]:
    """שומר את ההודעות האחרונות, ומתחיל תמיד מהודעת משתמשת כדי לא לנתק קריאת כלי מהתשובה שלה."""
    recent = list(messages[-limit:])
    while recent and not isinstance(recent[0], HumanMessage):
        recent.pop(0)
    return recent or list(messages[-1:])


def root_cause(exc: BaseException) -> str:
    """השרשרת המלאה של הסיבות (למשל SSL או DNS), לאבחון. הלוגים מסננים מפתחות."""
    parts = []
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        parts.append(f"{type(exc).__name__}: {exc}"[:300])
        exc = exc.__cause__ or exc.__context__
    return " <- ".join(parts)


def friendly_api_error(exc: Exception) -> str:
    name = type(exc).__name__
    text = str(exc).lower()
    if name == "AuthenticationError":
        return "מפתח ה-OpenAI לא תקין. צריך לבדוק את OPENAI_API_KEY בקובץ ‎.env."
    if name == "RateLimitError" and ("quota" in text or "insufficient" in text):
        return "נגמרה יתרת הקרדיט בחשבון OpenAI, ולכן לא אוכל לענות כרגע."
    if name == "RateLimitError":
        return "שירות OpenAI עמוס כרגע. נסי שוב בעוד רגע."
    if "Timeout" in name or "Connection" in name:
        return "אין חיבור לשירות OpenAI כרגע. כדאי לבדוק את החיבור לאינטרנט ולנסות שוב."
    return "אירעה שגיאה בפנייה למודל. נסי שוב, ואם זה חוזר כדאי לבדוק את הלוגים."


def make_agent_node(llm: BaseChatModel, tools: list):
    bound = llm.bind_tools(tools)

    def agent(state: AgentState) -> dict:
        system = SystemMessage(SYSTEM_PROMPT + "\n\n" + state.get("context", ""))
        try:
            reply = bound.invoke([system, *trim_history(state["messages"])])
        except Exception as exc:  # שגיאות API: OpenAI ו-langchain עוטפים בכמה סוגים
            log.warning("LLM call failed: %s; cause: %s", type(exc).__name__, root_cause(exc))
            return {"messages": [AIMessage(content=friendly_api_error(exc))], "last_error": type(exc).__name__}
        rounds = state.get("tool_rounds", 0) + (1 if getattr(reply, "tool_calls", None) else 0)
        return {"messages": [reply], "tool_rounds": rounds}

    return agent


def route_after_agent(state: AgentState) -> str:
    last = state["messages"][-1]
    calls = getattr(last, "tool_calls", None) if isinstance(last, AIMessage) else None
    if not calls:
        return "save_turn"
    if state.get("tool_rounds", 0) > MAX_TOOL_ROUNDS:
        return "finalize"
    if any(c["name"] in PROPOSAL_TOOL_NAMES for c in calls):
        return "build_proposal"
    return "tools"


def finalize(state: AgentState) -> dict:
    """מגבלת סבבים: עונים לכל קריאה פתוחה (כדי שההיסטוריה תישאר תקינה) ומסיימים."""
    last = state["messages"][-1]
    closing: list[AnyMessage] = [
        ToolMessage(content='{"ok": false, "error": "step limit reached; not executed"}', tool_call_id=c["id"])
        for c in getattr(last, "tool_calls", []) or []
    ]
    closing.append(
        AIMessage(content="לא הצלחתי להשלים את הבקשה בכמה צעדים סבירים. אפשר לנסח אותה שוב, אולי בחלקים קטנים יותר?")
    )
    return {"messages": closing, "last_error": "max_tool_rounds"}

"""
הגרף של DayPilot.

START -> load_context -> agent -(conditional)-> tools -> agent            (לולאת כלים)
                                       \\-> build_proposal -(conditional)-> human_approval -> apply_change -> agent
                                       |                    \\-> agent (הצעה לא תקינה / אין מה לשנות)
                                       \\-> save_turn -> END
                                       \\-> finalize -> save_turn         (מגבלת סבבים)

human_approval מחזיר Command(goto=...): אישור -> apply_change, דחייה או בקשת שינוי -> agent.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from daypilot.agent.nodes.approval import make_apply_change, make_build_proposal, make_human_approval, route_after_proposal
from daypilot.agent.nodes.context import make_load_context
from daypilot.agent.nodes.reasoning import finalize, make_agent_node, route_after_agent
from daypilot.agent.nodes.turn import make_save_turn
from daypilot.agent.state import AgentState
from daypilot.agent.tools.registry import PROPOSAL_TOOL_NAMES, build_tools
from daypilot.container import AppContainer


def make_sqlite_checkpointer(path: Path) -> BaseCheckpointSaver:
    from langgraph.checkpoint.sqlite import SqliteSaver

    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    return saver


def build_graph(container: AppContainer, llm: BaseChatModel, checkpointer: BaseCheckpointSaver):
    tools = build_tools(container)
    executable = [t for t in tools if t.name not in PROPOSAL_TOOL_NAMES]

    builder = StateGraph(AgentState)
    builder.add_node("load_context", make_load_context(container))
    builder.add_node("agent", make_agent_node(llm, tools))
    builder.add_node("tools", ToolNode(executable, handle_tool_errors=True))
    builder.add_node("build_proposal", make_build_proposal(container))
    builder.add_node("human_approval", make_human_approval(container))
    builder.add_node("apply_change", make_apply_change(container))
    builder.add_node("finalize", finalize)
    builder.add_node("save_turn", make_save_turn(container))

    builder.add_edge(START, "load_context")
    builder.add_edge("load_context", "agent")
    builder.add_conditional_edges(
        "agent",
        route_after_agent,
        {"tools": "tools", "build_proposal": "build_proposal", "save_turn": "save_turn", "finalize": "finalize"},
    )
    builder.add_edge("tools", "agent")
    builder.add_conditional_edges(
        "build_proposal", route_after_proposal, {"human_approval": "human_approval", "agent": "agent"}
    )
    # מ-human_approval אין קשת קבועה: ה-Command שהוא מחזיר מחליט
    builder.add_edge("apply_change", "agent")
    builder.add_edge("finalize", "save_turn")
    builder.add_edge("save_turn", END)

    return builder.compile(checkpointer=checkpointer)

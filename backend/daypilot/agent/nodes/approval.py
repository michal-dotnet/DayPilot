"""
build_proposal -> human_approval -> apply_change

build_proposal: מחשב הצעה (קריאה בלבד, בלי כתיבה למסד).
human_approval: interrupt() אמיתי. הגרף נעצר, המצב נשמר ב-Checkpointer, וממשיכים עם Command(resume=...).
apply_change: הכתיבה היחידה למסד, ורק אחרי אישור.

כמו בפרויקט המורה: ב-human_approval אין שום פעולה עם תופעות לוואי לפני interrupt(),
כי בהמשכה ה-node רץ שוב מההתחלה.
"""


import logging
from typing import Literal

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command, interrupt

from daypilot.agent.dates import DateParseError
from daypilot.agent.proposals import compute_proposal, format_proposal, has_changes, proposal_for_model
from daypilot.agent.state import AgentState
from daypilot.agent.tools.common import dumps
from daypilot.agent.tools.registry import PROPOSAL_TOOL_NAMES
from daypilot.container import AppContainer
from daypilot.domain.enums import ProposalStatus
from daypilot.domain.schemas import PlanProposal
from daypilot.services.errors import DayPilotError, StaleProposalError

log = logging.getLogger(__name__)

APPROVAL_ACTIONS = ("approve", "reject", "revise")


def _titles(container: AppContainer, user_id: int) -> dict[int, str]:
    with container.unit() as svc:
        return {t.id: t.title for t in svc.tasks.tasks.list(user_id, statuses=None)}


def make_build_proposal(container: AppContainer):
    tz = container.settings.timezone

    def build_proposal(state: AgentState) -> dict:
        last: AIMessage = state["messages"][-1]
        calls = list(last.tool_calls)
        main = next(c for c in calls if c["name"] in PROPOSAL_TOOL_NAMES)
        replies: list[ToolMessage] = [
            ToolMessage(
                content=dumps({"ok": False, "error": "not executed: call a propose_* tool alone; call this again afterwards"}),
                tool_call_id=c["id"],
            )
            for c in calls
            if c["id"] != main["id"]
        ]
        user_id = state["user_id"]
        try:
            proposal = compute_proposal(container, user_id, main["name"], main.get("args") or {})
        except (DayPilotError, DateParseError, KeyError, ValueError, TypeError) as exc:
            message = getattr(exc, "message", None) or str(exc)
            replies.append(ToolMessage(content=dumps({"ok": False, "error": message}), tool_call_id=main["id"]))
            return {"messages": replies, "pending_proposal": None, "proposal_call_id": None}

        titles = _titles(container, user_id)
        if not has_changes(proposal):
            summary = proposal_for_model(proposal, titles, tz)
            summary["status"] = "nothing_to_change" if proposal.feasible else "no_feasible_change"
            replies.append(ToolMessage(content=dumps(summary), tool_call_id=main["id"]))
            return {"messages": replies, "pending_proposal": None, "proposal_call_id": None}

        return {
            "messages": replies,
            "pending_proposal": proposal.model_dump(mode="json"),
            "proposal_call_id": main["id"],
        }

    return build_proposal


def route_after_proposal(state: AgentState) -> str:
    return "human_approval" if state.get("pending_proposal") else "agent"


def make_human_approval(container: AppContainer):
    tz = container.settings.timezone

    def human_approval(state: AgentState) -> Command[Literal["apply_change", "agent"]]:
        proposal = PlanProposal.model_validate(state["pending_proposal"])
        titles = _titles(container, state["user_id"])  # קריאה בלבד, בטוח להריץ שוב
        decision = interrupt(
            {
                "type": "proposal_approval",
                "proposal": state["pending_proposal"],
                "display": format_proposal(proposal, titles, tz),
                "question": "לאשר, לדחות או לבקש שינוי?",
                "actions": list(APPROVAL_ACTIONS),
            }
        )

        action = (decision or {}).get("action")
        feedback = str((decision or {}).get("feedback") or "")[:1000]
        if action == "approve":
            return Command(goto="apply_change")

        status = ProposalStatus.REVISED if action == "revise" else ProposalStatus.REJECTED
        with container.unit() as svc:
            svc.schedule.record_decision(state["user_id"], proposal, status, state.get("thread_id", ""))
        result = {
            "status": "user_requested_changes" if action == "revise" else "rejected_by_user",
            "feedback": feedback,
            "applied": False,
        }
        return Command(
            goto="agent",
            update={
                "messages": [ToolMessage(content=dumps(result), tool_call_id=state["proposal_call_id"])],
                "pending_proposal": None,
                "proposal_call_id": None,
            },
        )

    return human_approval


def make_apply_change(container: AppContainer):
    tz = container.settings.timezone

    def apply_change(state: AgentState) -> dict:
        proposal = PlanProposal.model_validate(state["pending_proposal"])
        call_id = state["proposal_call_id"]
        try:
            with container.unit() as svc:
                result = svc.schedule.apply_proposal(state["user_id"], proposal, state.get("thread_id", ""))
            titles = _titles(container, state["user_id"])
            content = {"ok": True, "applied": True, **result, "summary": proposal_for_model(proposal, titles, tz)}
        except StaleProposalError as exc:
            content = {"ok": False, "applied": False, "status": "stale", "error": exc.message,
                       "hint": "the data changed; call the same propose tool again to recompute"}
        except DayPilotError as exc:
            log.warning("apply failed: %s", exc.code)
            content = {"ok": False, "applied": False, "error": exc.message}
        return {
            "messages": [ToolMessage(content=dumps(content), tool_call_id=call_id)],
            "pending_proposal": None,
            "proposal_call_id": None,
        }

    return apply_change

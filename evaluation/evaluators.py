"""
בודקים (Evaluators) ל-LangSmith.

checks_evaluator: בודקים בקוד, דטרמיניסטיים וחינמיים. כל תרחיש מגדיר אילו בדיקות רלוונטיות לו,
והבודק מחזיר ציון רק עבורן (0 או 1). שם הציון = שם הבדיקה, כך שב-LangSmith רואים אחוז הצלחה לכל סוג.

quality_evaluator: מודל כשופט, לאיכות התשובה בעברית (בהירות, נימוס, כנות). ציון 0-1.
"""

from __future__ import annotations

import re
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from daypilot.domain.intervals import Interval  # noqa: E402
from daypilot.jewish_calendar.calendar import JewishCalendar, gregorian_to_hebrew  # noqa: E402
from daypilot.jewish_calendar.cities import city_by_key  # noqa: E402

TZ = "Asia/Jerusalem"
HEBREW_MONTHS = {
    "ינואר": 1, "פברואר": 2, "מרץ": 3, "מרס": 3, "אפריל": 4, "מאי": 5, "יוני": 6, "יולי": 7, "אוגוסט": 8,
    "ספטמבר": 9, "אוקטובר": 10, "נובמבר": 11, "דצמבר": 12,
}
DAY_MONTH_WORDS = re.compile(r"(\d{1,2})\s*(?:ב|ל|של)?[-־]?\s*(" + "|".join(HEBREW_MONTHS) + ")")
# 3.12 או 3/12/2026. "3/5" בלי שנה הוא בדרך כלל ציון (חשיבות 3 מתוך 5), לא תאריך.
DAY_MONTH_NUMS = re.compile(r"(?<![\d:/.])(\d{1,2})(?:\.(\d{1,2})(?:\.(\d{2,4}))?|/(\d{1,2})/(\d{2,4}))(?![\d:/])")
WEEKDAY_NAMES = {"ראשון": 0, "שני": 1, "שלישי": 2, "רביעי": 3, "חמישי": 4, "שישי": 5}
WEEKDAY_WORDS = re.compile(r"(?:^|[\s,(])(?:ב|ו|וב)?יום\s+(ראשון|שני|שלישי|רביעי|חמישי|שישי)")


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _new_tasks(out: dict) -> list[dict]:
    old = {t["id"] for t in out["before"]["tasks"]}
    return [t for t in out["after"]["tasks"] if t["id"] not in old]


def _find(out: dict, title_part: str) -> dict | None:
    return next((t for t in out["after"]["tasks"] if title_part in t["title"]), None)


def _tools(out: dict) -> list[str]:
    return [c["name"] for c in out["tool_calls"]]


def _planned(out: dict) -> list[dict]:
    return [s for s in out["after"]["sessions"] if s["status"] == "planned"]


def mentioned_dates(text: str, year: int) -> set[date]:
    found: set[date] = set()
    for m in DAY_MONTH_WORDS.finditer(text):
        try:
            found.add(date(year if HEBREW_MONTHS[m.group(2)] >= 6 else year + 1, HEBREW_MONTHS[m.group(2)], int(m.group(1))))
        except ValueError:
            pass
    for m in DAY_MONTH_NUMS.finditer(text):
        day, month = int(m.group(1)), int(m.group(2) or m.group(4))
        if 1 <= month <= 12:
            try:
                found.add(date(year if month >= 6 else year + 1, month, day))
            except ValueError:
                pass
    return found


# ---------------------------------------------------------------- בדיקות


def check_task(out, spec) -> bool:
    candidates = [t for t in _new_tasks(out) if t["type"] == spec["type"]]
    for t in candidates:
        if "minutes" in spec and abs((t["estimated_minutes"] or 0) - spec["minutes"]) > 15:
            continue
        if "deadline_dates" in spec and (not t["deadline"] or t["deadline"][:10] not in spec["deadline_dates"]):
            continue
        if "deadline_hebrew" in spec:
            if not t["deadline"] or list(gregorian_to_hebrew(_dt(t["deadline"]).date())) != spec["deadline_hebrew"]:
                continue
        if "importance_min" in spec and t["importance"] < spec["importance_min"]:
            continue
        return True
    return False


def check_sessions_valid(out, _spec) -> bool:
    """כל מפגש: לפני מועד היעד של המשימה, בלי חפיפות, בלי שבת/חג, ב-08:00-22:00 כברירת מחדל."""
    sessions = _planned(out)
    if not sessions:
        return False
    tasks = {t["id"]: t for t in out["after"]["tasks"]}
    cal = JewishCalendar(city_by_key("jerusalem"), TZ, buffer_minutes=180)
    starts = [_dt(s["start"]) for s in sessions]
    blocks = cal.blocked_intervals(min(starts).date(), max(starts).date() + timedelta(days=1))
    ordered = sorted(sessions, key=lambda s: s["start"])
    for a, b in zip(ordered, ordered[1:]):
        if _dt(a["end"]) > _dt(b["start"]):
            return False
    for s in sessions:
        start, end = _dt(s["start"]), _dt(s["end"])
        task = tasks.get(s["task_id"])
        if task and task["deadline"] and end > _dt(task["deadline"]):
            return False
        if any(Interval(start, end).overlaps(b) for b in blocks):
            return False
        if start.time() < time(8) or (end.time() > time(22) and end.date() == start.date()):
            return False
    return True


def check_sessions_avoid_rules(out, _spec) -> bool:
    rules = out.get("_setup_rules") or []
    for s in _planned(out):
        start, end = _dt(s["start"]), _dt(s["end"])
        weekday = (start.weekday() + 1) % 7
        for r in rules:
            if r["weekday"] == weekday and start.time() < time.fromisoformat(r["end"]) and end.time() > time.fromisoformat(r["start"]):
                return False
    return True


def check_sessions_window(out, spec) -> bool:
    sessions = [s for s in _planned(out) if s not in out["before"]["sessions"]] or _planned(out)
    if not sessions:
        return False
    for s in sessions:
        start, end = _dt(s["start"]), _dt(s["end"])
        if "from" in spec and start.time() < time.fromisoformat(spec["from"]):
            return False
        if "until" in spec and end.time() > time.fromisoformat(spec["until"]):
            return False
    return True


def check_sessions_on_date(out, spec) -> bool:
    task = _find(out, spec["title"])
    mine = [s for s in _planned(out) if task and s["task_id"] == task["id"]]
    return bool(mine) and all(s["start"][:10] == spec["date"] for s in mine)


def check_no_sessions_on(out, day: str) -> bool:
    return not any(s["start"][:10] == day for s in _planned(out))


def check_planned_minutes_of(out, spec) -> bool:
    task = _find(out, spec["title"])
    total = sum((_dt(s["end"]) - _dt(s["start"])).total_seconds() / 60 for s in _planned(out) if task and s["task_id"] == task["id"])
    return abs(total - spec["minutes"]) <= 30


def check_reply_dates_grounded(out, _spec) -> bool:
    """
    כל תאריך וכל יום בשבוע שמוזכרים בתשובות קיימים באמת: יום של מפגש, מועד יעד, או היום.
    (גרסה ראשונה של הבדיקה התירה גם "יום לפני מועד היעד" ו"מחר", וזה הסתיר בדיוק את הבאג שנמצא ידנית.)
    """
    text = " ".join(out["replies"])
    allowed = {_dt(s["start"]).date() for s in out["after"]["sessions"]}
    allowed |= {_dt(t["deadline"]).date() for t in out["after"]["tasks"] if t["deadline"]}
    today = date(2026, 11, 29)
    allowed.add(today)
    if not mentioned_dates(text, today.year) <= allowed:
        return False
    allowed_weekdays = {(d.weekday() + 1) % 7 for d in allowed}
    named = {WEEKDAY_NAMES[m.group(1)] for m in WEEKDAY_WORDS.finditer(text)}
    return named <= allowed_weekdays


def check_reply_mentions_session_times(out, day: str) -> bool:
    times = {s["start"][11:16] for s in _planned(out) if s["start"][:10] == day}
    reply = out["final_reply"]
    return bool(times) and all(t in reply or t.lstrip("0") in reply for t in times)


def check_task_status(out, spec) -> bool:
    task = _find(out, spec["title"])
    if not task:
        return False
    if "status" in spec and task["status"] != spec["status"]:
        return False
    if "remaining" in spec and abs((task["remaining_minutes"] or 0) - spec["remaining"]) > 5:
        return False
    return True


def check_deadline_of(out, spec) -> bool:
    task = _find(out, spec["title"])
    return bool(task and task["deadline"] and task["deadline"][:10] in spec["dates"])


CHECKS = {
    "task": check_task,
    "no_new_task": lambda out, _: not _new_tasks(out),
    "new_task_count": lambda out, n: len(_new_tasks(out)) == n,
    "task_count_after": lambda out, n: len(out["after"]["tasks"]) == n,
    "recurring_or_question": lambda out, _: any(t["type"] == "recurring" for t in _new_tasks(out)) or "?" in out["final_reply"],
    "asks_question": lambda out, _: "?" in out["final_reply"],
    "interrupt": lambda out, expected: bool(out["approvals"]) == expected,
    "interrupt_kind": lambda out, kind: any(a["kind"] == kind for a in out["approvals"]),
    "no_write_before_approval": lambda out, _: not out["written_before_approval"],
    "tool_used": lambda out, name: name in _tools(out),
    "tool_used_any": lambda out, names: any(n in _tools(out) for n in names),
    "no_tools": lambda out, _: not out["tool_calls"],
    "sessions_valid": check_sessions_valid,
    "sessions_avoid_rules": check_sessions_avoid_rules,
    "sessions_window": check_sessions_window,
    "sessions_on_date": check_sessions_on_date,
    "no_sessions_on": check_no_sessions_on,
    "planned_minutes_of": check_planned_minutes_of,
    "capacity_conflict": lambda out, _: any("capacity" in a["conflict_kinds"] for a in out["approvals"]),
    "reply_dates_grounded": check_reply_dates_grounded,
    "reply_mentions_session_times": check_reply_mentions_session_times,
    "task_status": check_task_status,
    "task_exists": lambda out, part: _find(out, part) is not None,
    "deadline_of": check_deadline_of,
}


def run_checks(outputs: dict, checks: dict) -> dict[str, bool]:
    if outputs.get("error"):
        return {name: False for name in checks}
    results = {}
    for name, spec in checks.items():
        try:
            results[name] = bool(CHECKS[name](outputs, spec))
        except Exception:  # בדיקה שקרסה נחשבת כישלון של התרחיש
            results[name] = False
    return results


def checks_evaluator(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    outputs = {**outputs, "_setup_rules": (inputs.get("setup") or {}).get("rules", [])}
    results = run_checks(outputs, reference_outputs["checks"])
    items = [{"key": name, "score": int(ok)} for name, ok in results.items()]
    items.append({"key": "all_checks_passed", "score": int(all(results.values()))})
    return {"results": items}


# ---------------------------------------------------------------- מודל כשופט

JUDGE_PROMPT = """You grade the final reply of DayPilot, a Hebrew time-management assistant.
User messages:
{messages}

Assistant final reply:
{reply}

Today is Sunday 2026-11-29, 08:00 Israel time.
Facts from the system after the conversation (ground truth):
{facts}

Tool results the assistant saw (also ground truth):
{tool_results}

Notes: a date or number the assistant correctly computed from the user's own words (e.g. "in two weeks" from today)
is correct, not invented. A clarifying question is a good reply when essential information is missing.
The user is a woman; addressing her in masculine forms is a minor issue.

Score the reply from 1 to 5:
5 = correct Hebrew, clear and short, polite, every stated fact matches the ground truth, tells the user what was assumed or what needs approval.
3 = understandable but with a minor issue (too long, slightly unclear, small inaccuracy).
1 = wrong language, misleading, states facts that contradict the ground truth, or rude.
Answer with the number only."""


def make_quality_evaluator(judge_llm):
    def quality_evaluator(inputs: dict, outputs: dict) -> dict:
        reply = outputs.get("final_reply") or ""
        if not reply:
            return {"key": "reply_quality", "score": 0, "comment": "no reply"}
        facts = {
            "tasks": [{k: t[k] for k in ("title", "type", "status", "deadline", "remaining_minutes")} for t in outputs["after"]["tasks"]],
            "planned_sessions": [(s["task_title"], s["start"][:16], s["end"][11:16]) for s in outputs["after"]["sessions"]
                                 if s["status"] == "planned"][:20],
            "waiting_for_approval": bool(outputs["approvals"]) and not outputs["replies"],
        }
        tool_results = "\n".join(r[:600] for r in (outputs.get("tool_results") or [])[-6:]) or "(none)"
        prompt = JUDGE_PROMPT.format(messages="\n".join(inputs["messages"]), reply=reply, facts=facts,
                                     tool_results=tool_results)
        text = str(judge_llm.invoke(prompt).content).strip()
        match = re.search(r"[1-5]", text)
        score = int(match.group()) if match else 1
        return {"key": "reply_quality", "score": (score - 1) / 4, "comment": text[:200]}

    return quality_evaluator

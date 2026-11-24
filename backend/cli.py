"""
צ'אט עם DayPilot בטרמינל, לבדיקות (כמו main.py בפרויקט המורה).

הרצה מתיקיית הפרויקט:
    python backend/cli.py            # שיחה חדשה
    python backend/cli.py t-abc123   # המשך שיחה קיימת (כולל הצעה שממתינה לאישור)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from daypilot.agent.llm import MissingApiKeyError  # noqa: E402
from daypilot.agent.runner import AgentRunner, TurnResult  # noqa: E402
from daypilot.container import AppContainer  # noqa: E402
from daypilot.utils.logging import setup_logging  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")


def ask_decision(approval: dict) -> tuple[str, str]:
    print("\n" + "=" * 60)
    print(approval.get("display", ""))
    print("=" * 60)
    print(approval.get("question", ""))
    while True:
        choice = input("[a] אישור  [r] דחייה  [v] בקשת שינוי: ").strip().lower()
        if choice == "a":
            return "approve", ""
        if choice == "r":
            return "reject", input("סיבה (אפשר להשאיר ריק): ")
        if choice == "v":
            return "revise", input("מה לשנות? ")


def show(result: TurnResult, runner: AgentRunner) -> None:
    while result.approval is not None:
        action, feedback = ask_decision(result.approval)
        result = runner.resume(result.thread_id, action, feedback)
    if result.reply:
        print(f"\nDayPilot: {result.reply}\n")


def main() -> None:
    setup_logging()
    container = AppContainer()
    try:
        runner = AgentRunner(container)
    except MissingApiKeyError as exc:
        print(exc)
        return
    user_id = container.default_user_id()
    thread_id = sys.argv[1] if len(sys.argv) > 1 else runner.new_thread_id()
    print(f"שיחה: {thread_id}  (יציאה: exit)")

    pending = runner.pending(thread_id)
    if pending:
        show(TurnResult(thread_id, None, pending), runner)

    while True:
        try:
            text = input("את/ה: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if text.lower() in ("exit", "quit", "יציאה"):
            break
        if not text:
            continue
        show(runner.send(user_id, thread_id, text), runner)


if __name__ == "__main__":
    main()

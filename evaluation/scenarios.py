"""
תרחישי הבדיקה של DayPilot (ה-Dataset ב-LangSmith).

כל תרחיש:
- inputs.messages: מה שהמשתמשת כותבת (תור אחד או יותר).
- inputs.setup: מצב התחלתי (משימות, שעות קבועות, האם לשבץ מראש).
- inputs.decision: מה עונים על הצעה שממתינה לאישור (approve / reject).
- outputs.checks: מה הבודקים צריכים לוודא. כל בודק רץ רק על תרחישים שבהם הוא רלוונטי.

השעון קבוע: יום ראשון 29.11.2026, 08:00 שעון ישראל. כך התוצאות ניתנות להשוואה בין ניסויים.
"""

from datetime import date, timedelta

NOW = "2026-11-29T08:00:00+02:00"
TODAY = date(2026, 11, 29)  # יום ראשון


def d(days: int) -> str:
    return (TODAY + timedelta(days=days)).isoformat()


HISTORY = {"title": "מבחן בהיסטוריה", "type": "scheduled", "deadline_days": 4, "minutes": 480, "importance": 3}
ENGLISH = {"title": "עבודה באנגלית", "type": "scheduled", "deadline_days": 6, "minutes": 240, "importance": 2}

SCENARIOS: list[dict] = [
    # ---------------- חילוץ משימות משפה טבעית ----------------
    {
        "id": "extract_exam_week",
        "category": "extraction",
        "messages": ["יש לי מבחן בעוד שבוע ואני צריכה ללמוד 20 שעות"],
        "checks": {
            "task": {"type": "scheduled", "deadline_dates": [d(7)], "minutes": 1200},
            "interrupt": True, "no_write_before_approval": True, "sessions_valid": True, "reply_dates_grounded": True,
        },
    },
    {
        "id": "extract_project_ten_days",
        "category": "extraction",
        "messages": ["יש לי פרויקט להגשה בעוד עשרה ימים, ואני צריכה להשקיע בו 12 שעות"],
        "checks": {
            "task": {"type": "scheduled", "deadline_dates": [d(10)], "minutes": 720},
            "interrupt": True, "sessions_valid": True, "reply_dates_grounded": True,
        },
    },
    {
        "id": "extract_open_notebook",
        "category": "extraction",
        "messages": ["אני צריכה לקנות מחברת"],
        "checks": {"task": {"type": "open"}, "interrupt": False},
    },
    {
        "id": "extract_open_call",
        "category": "extraction",
        "messages": ["תזכיר לי להתקשר לסבתא"],
        "checks": {"task": {"type": "open"}, "interrupt": False},
    },
    {
        "id": "extract_weekly_quiz",
        "category": "extraction",
        "messages": ["יש לי בוחן בכל יום רביעי"],
        "checks": {"recurring_or_question": True},
    },
    {
        "id": "extract_tomorrow_exam",
        "category": "extraction",
        "messages": ["מחר יש לי מבחן בתנ\"ך, אני צריכה עוד 3 שעות חזרה"],
        "checks": {"task": {"type": "scheduled", "deadline_dates": [d(1)], "minutes": 180}, "interrupt": True},
    },
    {
        "id": "extract_next_thursday",
        "category": "extraction",
        "messages": ["עבודה בסטטיסטיקה להגשה ביום חמישי הבא, בערך 5 שעות"],
        "checks": {"task": {"type": "scheduled", "deadline_dates": [d(4), d(11)], "minutes": 300}},
    },
    {
        "id": "extract_hebrew_date",
        "category": "extraction",
        "messages": ["יש לי הגשה בט\"ו בשבט, 6 שעות עבודה"],
        "checks": {"task": {"type": "scheduled", "deadline_hebrew": [5787, 11, 15], "minutes": 360},
                   "tool_used": "resolve_hebrew_date"},
    },
    {
        "id": "extract_importance",
        "category": "extraction",
        "messages": ["יש לי מבחן חשוב מאוד במתמטיקה בעוד 5 ימים, צריכה 15 שעות"],
        "checks": {"task": {"type": "scheduled", "deadline_dates": [d(5)], "minutes": 900, "importance_min": 4}},
    },
    # ---------------- מידע חסר ----------------
    {
        "id": "missing_everything",
        "category": "missing_info",
        "messages": ["יש לי מבחן"],
        "checks": {"no_new_task": True, "asks_question": True, "interrupt": False},
    },
    {
        "id": "missing_hours",
        "category": "missing_info",
        "messages": ["יש לי פרויקט להגשה בעוד שבועיים"],
        "checks": {"no_new_task": True, "asks_question": True},
    },
    {
        "id": "missing_which_task",
        "category": "missing_info",
        "setup": {"tasks": [HISTORY, ENGLISH]},
        "messages": ["תמחק את המשימה"],
        "checks": {"asks_question": True, "interrupt": False, "task_count_after": 2},
    },
    # ---------------- כללי אישור ----------------
    {
        "id": "policy_delete_needs_approval",
        "category": "approval_policy",
        "setup": {"tasks": [HISTORY], "schedule": True},
        "decision": "reject",
        "messages": ["תמחק את המבחן בהיסטוריה"],
        "checks": {"interrupt": True, "interrupt_kind": "delete_task", "no_write_before_approval": True,
                   "task_exists": "היסטוריה"},
    },
    {
        "id": "policy_deadline_needs_approval",
        "category": "approval_policy",
        "setup": {"tasks": [HISTORY], "schedule": True},
        "messages": ["המבחן בהיסטוריה נדחה ביומיים"],
        "checks": {"interrupt": True, "interrupt_kind": "deadline_change", "no_write_before_approval": True,
                   "deadline_of": {"title": "היסטוריה", "dates": [d(6)]}},
    },
    {
        "id": "policy_duration_needs_approval",
        "category": "approval_policy",
        "setup": {"tasks": [HISTORY], "schedule": True},
        "messages": ["אני צריכה עוד 4 שעות למבחן בהיסטוריה"],
        "checks": {"interrupt": True, "interrupt_kind": "duration_change", "no_write_before_approval": True},
    },
    {
        "id": "policy_rename_is_automatic",
        "category": "approval_policy",
        "setup": {"tasks": [HISTORY]},
        "messages": ["תשני את השם של המבחן בהיסטוריה ל'מבחן בהיסטוריה של עם ישראל'"],
        "checks": {"interrupt": False, "tool_used": "update_task_details", "task_exists": "עם ישראל"},
    },
    {
        "id": "policy_done_is_automatic",
        "category": "approval_policy",
        "setup": {"tasks": [HISTORY], "schedule": True},
        "messages": ["סיימתי ללמוד למבחן בהיסטוריה"],
        "checks": {"interrupt": False, "task_status": {"title": "היסטוריה", "status": "done"}},
    },
    {
        "id": "policy_progress_is_automatic",
        "category": "approval_policy",
        "setup": {"tasks": [HISTORY], "schedule": True},
        "messages": ["עבדתי שעתיים על ההיסטוריה"],
        "checks": {"interrupt": False, "task_status": {"title": "היסטוריה", "remaining": 360}},
    },
    # ---------------- תכנון ושיבוץ ----------------
    {
        "id": "schedule_existing_task",
        "category": "scheduling",
        "setup": {"tasks": [HISTORY]},
        "messages": ["תשבצי לי זמן ללמוד להיסטוריה"],
        "checks": {"interrupt": True, "sessions_valid": True, "planned_minutes_of": {"title": "היסטוריה", "minutes": 480},
                   "reply_dates_grounded": True},
    },
    {
        "id": "schedule_respects_classes",
        "category": "scheduling",
        "setup": {"tasks": [HISTORY], "rules": [{"weekday": w, "start": "09:00", "end": "14:00", "kind": "class"} for w in range(5)]},
        "messages": ["תשבצי לי את הלמידה להיסטוריה"],
        "checks": {"interrupt": True, "sessions_valid": True, "sessions_avoid_rules": True},
    },
    {
        "id": "schedule_evenings_only",
        "category": "scheduling",
        "messages": ["יש לי מבחן ביום חמישי ואני צריכה 8 שעות, אני יכולה ללמוד רק בערבים"],
        "checks": {"interrupt": True, "sessions_valid": True, "sessions_window": {"from": "17:00"}, "reply_dates_grounded": True},
    },
    {
        "id": "query_tomorrow",
        "category": "scheduling",
        "setup": {"tasks": [HISTORY], "schedule": True},
        "messages": ["מה יש לי מחר?"],
        "checks": {"interrupt": False, "tool_used_any": ["get_schedule", "check_availability"], "reply_mentions_session_times": d(1)},
    },
    {
        "id": "query_free_time",
        "category": "scheduling",
        "messages": ["מתי אני פנויה ביום שלישי?"],
        "checks": {"interrupt": False, "tool_used_any": ["check_availability", "get_schedule"]},
    },
    # ---------------- התנגשויות ----------------
    {
        "id": "conflict_two_tasks",
        "category": "conflicts",
        "setup": {"tasks": [
            {"title": "מבחן בכימיה", "type": "scheduled", "deadline_days": 2, "minutes": 600},
            {"title": "פרויקט בתכנות", "type": "scheduled", "deadline_days": 2, "minutes": 480},
        ]},
        "decision": "reject",
        "messages": ["תשבצי את שתי המשימות"],
        "checks": {"interrupt": True, "capacity_conflict": True, "no_write_before_approval": True},
    },
    {
        "id": "conflict_not_enough_time",
        "category": "conflicts",
        "decision": "reject",
        "messages": ["יש לי מבחן מחר בבוקר ואני צריכה ללמוד 15 שעות"],
        "checks": {"capacity_conflict": True},
    },
    # ---------------- שינוי ידני של תוכנית ----------------
    {
        "id": "manual_move_to_tuesday",
        "category": "manual_change",
        "setup": {"tasks": [{"title": "מבחן בביולוגיה", "type": "scheduled", "deadline_days": 3, "minutes": 240}], "schedule": True},
        "messages": ["יש לי מבחן ביום רביעי. אני רוצה להעביר את כל הלמידה ליום שלישי בלבד"],
        "checks": {"interrupt": True, "interrupt_kind": "reschedule", "sessions_on_date": {"title": "ביולוגיה", "date": d(2)},
                   "reply_dates_grounded": True},
    },
    {
        "id": "manual_mornings_only",
        "category": "manual_change",
        "setup": {"tasks": [HISTORY], "schedule": True},
        "messages": ["אני רוצה ללמוד להיסטוריה רק בבקרים, עד 12 בצהריים"],
        "checks": {"interrupt": True, "sessions_window": {"until": "12:00"}},
    },
    {
        "id": "manual_day_off",
        "category": "manual_change",
        "setup": {"tasks": [HISTORY], "schedule": True},
        "messages": ["מחר אני לא פנויה בכלל, תעדכני את התוכנית"],
        "checks": {"tool_used": "add_date_exception", "no_sessions_on": d(1)},
    },
    # ---------------- בקשות מורכבות ----------------
    {
        "id": "complex_two_new_tasks",
        "category": "complex",
        "messages": ["יש לי מבחן בעוד שבוע, 10 שעות, ופרויקט בעוד 10 ימים, 6 שעות. תשבצי הכל"],
        "checks": {"new_task_count": 2, "interrupt": True, "sessions_valid": True, "reply_dates_grounded": True},
    },
    {
        "id": "complex_progress_and_move",
        "category": "complex",
        "setup": {"tasks": [HISTORY], "schedule": True},
        "messages": ["למדתי שעה להיסטוריה, ואת מה שנשאר תעבירי ליום רביעי"],
        "checks": {"task_status": {"title": "היסטוריה", "remaining": 420}, "interrupt": True,
                   "sessions_on_date": {"title": "היסטוריה", "date": d(3)}},
    },
    # ---------------- נאמנות התשובה לתוכנית (הבאג שנמצא בהרצה ידנית) ----------------
    {
        "id": "grounding_evenings_week",
        "category": "grounding",
        "messages": ["יש לי מבחן בעוד שבוע ואני צריכה ללמוד 10 שעות, רק בערבים"],
        "checks": {"interrupt": True, "sessions_window": {"from": "17:00"}, "reply_dates_grounded": True},
    },
    {
        "id": "grounding_which_days",
        "category": "grounding",
        "setup": {"tasks": [HISTORY]},
        "messages": ["תשבצי לי את הלמידה להיסטוריה ותגידי לי באילו ימים יצא"],
        "checks": {"interrupt": True, "reply_dates_grounded": True},
    },
    {
        "id": "grounding_until_when",
        "category": "grounding",
        "setup": {"tasks": [ENGLISH]},
        "messages": ["תשבצי את העבודה באנגלית. עד איזה יום אני אסיים איתה?"],
        "checks": {"interrupt": True, "reply_dates_grounded": True},
    },
    # ---------------- מחוץ לתחום ----------------
    {
        "id": "out_of_scope",
        "category": "scope",
        "messages": ["מה מזג האוויר מחר?"],
        "checks": {"no_new_task": True, "interrupt": False, "no_tools": True},
    },
]

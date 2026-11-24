"""מצב המערכת לתצוגה: משתמשת, הגדרות, משימות, לוח שנה, Dashboard והתקדמות."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query

from daypilot.api.deps import AppState, state
from daypilot.domain.schemas import DateExceptionIn, PreferencesUpdate, WeeklyRuleIn
from daypilot.services.errors import ValidationError

router = APIRouter(prefix="/api")


@router.get("/health")
def health(app: AppState = Depends(state)) -> dict:
    settings = app.container.settings
    return {
        "ok": True,
        "model": settings.model_name,
        "openai_key": bool(settings.openai_api_key),
        "tracing": bool(settings.langsmith_api_key and settings.langsmith_tracing),
    }


@router.get("/me")
def me(app: AppState = Depends(state)) -> dict:
    with app.container.unit() as svc:
        user = svc.settings.users.get(app.user_id)
        prefs = svc.settings.preferences(app.user_id)
        return {
            "id": user.id,
            "name": user.name,
            "ui_language": user.ui_language,
            "city": user.city.key if user.city else None,
            "cities": [{"key": c.key, "name_he": c.name_he, "name_en": c.name_en} for c in svc.settings.users.cities()],
            "preferences": {
                "min_session_minutes": prefs.min_session_minutes,
                "max_session_minutes": prefs.max_session_minutes,
                "daily_max_minutes": prefs.daily_max_minutes,
                "shabbat_buffer_minutes": prefs.shabbat_buffer_minutes,
                "block_chol_hamoed": prefs.block_chol_hamoed,
            },
            "rules": [
                {"id": r.id, "weekday": r.weekday, "start_time": str(r.start_time)[:5], "end_time": str(r.end_time)[:5],
                 "kind": r.kind, "label": r.label}
                for r in svc.settings.users.rules(app.user_id)
            ],
        }


@router.patch("/settings")
def update_settings(data: PreferencesUpdate, app: AppState = Depends(state)) -> dict:
    with app.container.unit() as svc:
        svc.settings.update_preferences(app.user_id, data)
    return me(app)


@router.post("/settings/rules")
def add_rule(data: WeeklyRuleIn, app: AppState = Depends(state)) -> dict:
    with app.container.unit() as svc:
        rule = svc.settings.add_rule(app.user_id, data)
        return {"id": rule.id}


@router.delete("/settings/rules/{rule_id}")
def delete_rule(rule_id: int, app: AppState = Depends(state)) -> dict:
    with app.container.unit() as svc:
        svc.settings.delete_rule(app.user_id, rule_id)
    return {"ok": True}


@router.post("/settings/exceptions")
def add_exception(data: DateExceptionIn, app: AppState = Depends(state)) -> dict:
    with app.container.unit() as svc:
        ex = svc.settings.add_exception(app.user_id, data)
        return {"id": ex.id}


@router.get("/tasks")
def tasks(include_done: bool = False, app: AppState = Depends(state)) -> list[dict]:
    with app.container.unit() as svc:
        return [svc.tasks.view(t).model_dump(mode="json") for t in svc.tasks.list(app.user_id, include_done)]


@router.get("/calendar")
def calendar(start: date, end: date, app: AppState = Depends(state)) -> dict:
    if end < start or (end - start) > timedelta(days=62):
        raise ValidationError("range must be 0-62 days")
    with app.container.unit() as svc:
        return svc.views.calendar(app.user_id, start, end)


@router.get("/dashboard")
def dashboard(app: AppState = Depends(state)) -> dict:
    with app.container.unit() as svc:
        return svc.views.dashboard(app.user_id)


@router.get("/progress")
def progress(days: int = Query(14, ge=1, le=90), app: AppState = Depends(state)) -> dict:
    with app.container.unit() as svc:
        return svc.views.progress_report(app.user_id, days)

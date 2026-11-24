"""בדיקות ל-API: נתיבי תצוגה, הגדרות, וזרימת צ'אט מלאה עם אישור (מודל מזויף)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from daypilot.agent.llm import MissingApiKeyError
from daypilot.agent.runner import AgentRunner
from daypilot.api.app import create_app
from daypilot.config import Settings
from daypilot.container import AppContainer
from tests.conftest import START_DAY
from tests.fakes import ScriptedModel, call, say


def day(n: int) -> str:
    return (START_DAY + timedelta(days=n)).isoformat()


@pytest.fixture
def container(tmp_path, clock):
    return AppContainer(settings=Settings(_env_file=None, data_dir=tmp_path), clock=clock)


def client_with(container, script):
    model = ScriptedModel(script=list(script))
    app = create_app(container, runner_factory=lambda c: AgentRunner(c, llm=model, checkpointer=InMemorySaver()))
    return TestClient(app), model


def test_health_and_me(container):
    client, _ = client_with(container, [])
    assert client.get("/api/health").json()["ok"] is True
    me = client.get("/api/me").json()
    assert me["city"] == "jerusalem"
    assert any(c["key"] == "bnei_brak" for c in me["cities"])


def test_settings_validation_and_update(container):
    client, _ = client_with(container, [])
    bad = client.patch("/api/settings", json={"city_key": "atlantis"})
    assert bad.status_code == 400 and bad.json()["code"] == "invalid"
    ok = client.patch("/api/settings", json={"daily_max_minutes": 300, "city_key": "haifa"}).json()
    assert ok["preferences"]["daily_max_minutes"] == 300 and ok["city"] == "haifa"
    assert client.patch("/api/settings", json={"daily_max_minutes": 5}).status_code == 422
    rule = client.post("/api/settings/rules", json={"weekday": 0, "start_time": "09:00", "end_time": "14:00", "kind": "class"})
    assert rule.status_code == 200
    assert client.get("/api/me").json()["rules"][0]["kind"] == "class"


def test_chat_flow_with_approval_and_views(container):
    client, _ = client_with(container, [
        call("create_task", title="מבחן", task_type="scheduled", deadline=day(4), estimated_minutes=240),
        call("propose_schedule", reason="שיבוץ", task_ids=[1]),
        say("שובץ."),
    ])
    thread = client.post("/api/chat/threads").json()["id"]
    first = client.post(f"/api/chat/threads/{thread}/messages", json={"text": "מבחן ביום חמישי, 4 שעות"}).json()
    assert first["reply"] is None and first["approval"]["type"] == "proposal_approval"

    blocked = client.post(f"/api/chat/threads/{thread}/messages", json={"text": "עוד משהו"})
    assert blocked.status_code == 409 and blocked.json()["code"] == "pending_approval"

    history = client.get(f"/api/chat/threads/{thread}").json()
    assert history["approval"] is not None and history["messages"][0]["role"] == "user"

    done = client.post(f"/api/chat/threads/{thread}/decision", json={"action": "approve"}).json()
    assert done["reply"] == "שובץ."

    tasks = client.get("/api/tasks").json()
    assert tasks[0]["scheduled_minutes"] == 240

    cal = client.get("/api/calendar", params={"start": day(0), "end": day(6)}).json()
    assert len(cal["days"]) == 7 and cal["sessions"]
    assert any(b["kind"] == "rest" and b["label"] for b in cal["blocks"])  # שבת בשבוע הזה

    dash = client.get("/api/dashboard").json()
    assert dash["counts"]["active"] == 1 and len(dash["week"]) == 7
    assert dash["upcoming_deadlines"][0]["title"] == "מבחן"

    progress = client.get("/api/progress").json()
    assert progress["tasks"][0]["estimated_minutes"] == 240

    assert client.delete(f"/api/chat/threads/{thread}").json()["ok"] is True
    assert client.get("/api/chat/threads").json() == []
    assert len(client.get("/api/tasks").json()) == 1  # מחיקת היסטוריה לא מוחקת משימות


def test_invalid_decision_and_calendar_range(container):
    client, _ = client_with(container, [])
    assert client.post("/api/chat/threads/t1/decision", json={"action": "maybe"}).status_code == 422
    assert client.get("/api/calendar", params={"start": day(5), "end": day(0)}).status_code == 400


def test_missing_api_key_returns_503(container):
    def no_key(_c):
        raise MissingApiKeyError("OPENAI_API_KEY missing")

    client = TestClient(create_app(container, runner_factory=no_key))
    response = client.post("/api/chat/threads/t1/messages", json={"text": "היי"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "missing_api_key"


def test_dashboard_unreported_sessions_and_evening_hebrew_date(container, clock):
    from datetime import datetime as _dt

    client, _ = client_with(container, [
        call("create_task", title="מבחן", task_type="scheduled", deadline=day(4), estimated_minutes=240),
        call("propose_schedule", reason="שיבוץ", task_ids=[1]),
        say("שובץ."),
    ])
    thread = client.post("/api/chat/threads").json()["id"]
    client.post(f"/api/chat/threads/{thread}/messages", json={"text": "מבחן, 4 שעות"})
    client.post(f"/api/chat/threads/{thread}/decision", json={"action": "approve"})

    morning = client.get("/api/dashboard").json()
    assert morning["unreported_sessions"] == [] and morning["hebrew_date_tonight"] is None

    first = min(client.get("/api/calendar", params={"start": day(0), "end": day(6)}).json()["sessions"],
                key=lambda s: s["start"])
    clock.set(_dt.fromisoformat(first["end"]) + timedelta(minutes=1))
    after = client.get("/api/dashboard").json()
    assert after["unreported_sessions"][0]["task_title"] == "מבחן"
    assert after["needs_scheduling"] == []  # מפגש שעבר בלי דיווח הוא לא "חוסר בשיבוץ"

    from tests.conftest import L
    clock.set(L(START_DAY, 23))
    assert client.get("/api/dashboard").json()["hebrew_date_tonight"]


def test_shutdown_requires_header_and_run_py(container):
    client, _ = client_with(container, [])
    assert client.post("/api/system/shutdown").status_code == 403
    assert client.post("/api/system/shutdown", headers={"X-DayPilot": "1"}).status_code == 409


def test_shutdown_stops_uvicorn_server(container):
    class FakeServer:
        should_exit = False

    client, _ = client_with(container, [])
    server = FakeServer()
    client.app.state.uvicorn_server = server
    assert client.post("/api/system/shutdown", headers={"X-DayPilot": "1"}).json()["ok"] is True
    assert server.should_exit is True


def test_exam_work_style_is_saved_and_shown(container):
    client, _ = client_with(container, [
        call("create_task", title="מבחן בהיסטוריה", task_type="scheduled", deadline=day(6), estimated_minutes=600,
             work_style="exam"),
        say("נוצרה."),
    ])
    thread = client.post("/api/chat/threads").json()["id"]
    client.post(f"/api/chat/threads/{thread}/messages", json={"text": "מבחן בהיסטוריה בשבוע הבא, 10 שעות"})
    tasks = client.get("/api/tasks").json()
    assert tasks[0]["work_style"] == "exam"

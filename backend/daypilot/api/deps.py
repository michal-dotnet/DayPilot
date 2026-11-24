"""תלויות משותפות לנתיבי ה-API: הקונטיינר, המשתמשת, והאגנט (נוצר בפעם הראשונה שצריך אותו)."""

from __future__ import annotations

import threading

from fastapi import HTTPException, Request

from daypilot.agent.llm import MissingApiKeyError
from daypilot.agent.runner import AgentRunner
from daypilot.container import AppContainer


class AppState:
    def __init__(self, container: AppContainer, runner_factory=None):
        self.container = container
        self.user_id = container.default_user_id()
        self._runner_factory = runner_factory or (lambda c: AgentRunner(c))
        self._runner: AgentRunner | None = None
        self._runner_lock = threading.Lock()
        # משתמשת אחת: תור אחד של האגנט בכל רגע, כדי ששתי בקשות לא יכתבו לאותה שיחה במקביל
        self.agent_lock = threading.Lock()

    def runner(self) -> AgentRunner:
        with self._runner_lock:
            if self._runner is None:
                try:
                    self._runner = self._runner_factory(self.container)
                except MissingApiKeyError as exc:
                    raise HTTPException(status_code=503, detail={"code": "missing_api_key", "error": str(exc)}) from exc
            return self._runner


def state(request: Request) -> AppState:
    return request.app.state.daypilot

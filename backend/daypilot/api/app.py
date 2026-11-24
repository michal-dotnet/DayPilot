"""
אפליקציית FastAPI.

- /api/...  : הנתיבים של הממשק.
- /         : הממשק הבנוי (frontend/dist), אם קיים. בפיתוח Vite מגיש את הממשק ומפנה את /api לכאן.

השרת מאזין רק ל-127.0.0.1 (ההגדרה ב-run.py), ו-CORS מותר רק לכתובת הפיתוח המקומית.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from daypilot.agent.runner import PendingApprovalError
from daypilot.api.deps import AppState
from daypilot.api.routes import chat, views
from daypilot.config import PROJECT_ROOT
from daypilot.container import AppContainer
from daypilot.services.errors import DayPilotError, NotFoundError, StaleProposalError

log = logging.getLogger(__name__)
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"


def create_app(container: AppContainer | None = None, runner_factory=None) -> FastAPI:
    app = FastAPI(title="DayPilot", version="1.0")
    app.state.daypilot = AppState(container or AppContainer(), runner_factory)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(DayPilotError)
    def _business_error(_request: Request, exc: DayPilotError):
        status = 404 if isinstance(exc, NotFoundError) else 409 if isinstance(exc, StaleProposalError) else 400
        return JSONResponse(status_code=status, content={"code": exc.code, "error": exc.message, "details": exc.details})

    @app.exception_handler(PendingApprovalError)
    def _pending(_request: Request, exc: PendingApprovalError):
        return JSONResponse(status_code=409, content={"code": "pending_approval", "error": str(exc)})

    @app.exception_handler(Exception)
    def _unexpected(_request: Request, exc: Exception):
        log.exception("unexpected error: %s", type(exc).__name__)
        return JSONResponse(status_code=500, content={"code": "internal", "error": "internal error, see server logs"})

    app.include_router(views.router)
    app.include_router(chat.router)

    @app.post("/api/system/shutdown", include_in_schema=False)
    def shutdown(request: Request):
        # כותרת מותאמת מחייבת בקשת preflight, ולכן אתר זר בדפדפן לא יכול לכבות את השרת.
        if request.headers.get("x-daypilot") != "1":
            return JSONResponse(status_code=403, content={"code": "forbidden", "error": "missing header"})
        server = getattr(app.state, "uvicorn_server", None)
        if server is None:
            return JSONResponse(status_code=409, content={"code": "not_supported", "error": "server was not started by run.py"})
        log.info("shutdown requested from the UI")
        server.should_exit = True
        return {"ok": True}

    if FRONTEND_DIST.exists():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            file = FRONTEND_DIST / path
            if path and file.is_file():
                return FileResponse(file)
            return FileResponse(FRONTEND_DIST / "index.html")

    return app

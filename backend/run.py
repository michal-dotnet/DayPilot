"""
הפעלת השרת של DayPilot.

הרצה מתיקיית הפרויקט:
    python backend/run.py

ואז לפתוח בדפדפן: http://127.0.0.1:8000  (אחרי בניית הממשק)
בפיתוח של הממשק: npm run dev בתיקייה frontend, ולפתוח http://localhost:5173
"""

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _redirect_output_if_windowless() -> None:
    """בהפעלה מהאייקון (pythonw, --windowless) אין חלון. הפלט נכתב לקובץ data/server.log."""
    if "--windowless" not in sys.argv and sys.stdout is not None and sys.stderr is not None:
        return
    log_dir = Path(__file__).resolve().parents[1] / "data"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "server.log"
    if log_file.exists() and log_file.stat().st_size > 5 * 1024 * 1024:
        log_file.replace(log_dir / "server.old.log")  # שומרים קובץ קודם אחד בלבד
    stream = open(log_file, "a", encoding="utf-8", buffering=1)  # noqa: SIM115 - פתוח לכל חיי התהליך
    sys.stdout = sys.stderr = stream


def main() -> None:
    # ההפניה לקובץ לפני כל import כבד, כדי ששגיאת טעינה תיכתב ללוג
    _redirect_output_if_windowless()
    try:
        import uvicorn

        from daypilot.api.app import create_app
        from daypilot.config import get_settings
        from daypilot.utils.logging import setup_logging

        setup_logging()
        settings = get_settings()
        app = create_app()
        server = uvicorn.Server(uvicorn.Config(app, host=settings.api_host, port=settings.api_port, log_level="info"))
        app.state.uvicorn_server = server  # מאפשר כפתור "יציאה" בממשק
        server.run()
    except Exception:
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()

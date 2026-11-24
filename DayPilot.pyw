"""
מפעיל של DayPilot (לחיצה כפולה על האייקון).

1. אם השרת כבר פועל: פותח את הדפדפן.
2. אחרת: מפעיל את השרת ברקע, בלי חלון, מחכה שיעלה, ופותח את הדפדפן.

הרצה עם --background מפעילה את השרת בלי לפתוח דפדפן (להפעלה אוטומטית עם Windows).
הפלט של השרת נכתב ל-data/server.log.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STARTUP_TIMEOUT_S = 60


def _port() -> int:
    """הפורט מ-.env (API_PORT), או 8000."""
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "API_PORT" and value.strip().isdigit():
                return int(value.strip())
    return 8000


# בלי פרוקסי: השרת מקומי, ופרוקסי/סינון של Windows לא צריך לראות את הבקשה
_LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _is_up(url: str) -> bool:
    try:
        with _LOCAL.open(f"{url}/api/health", timeout=1) as resp:
            return resp.status == 200
    except OSError:
        return False


def _message(text: str) -> None:
    """חלון הודעה של Windows (אין חלון CMD להציג בו שגיאות)."""
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, "DayPilot", 0x10)
    except Exception:  # noqa: BLE001 - לא Windows
        print(text, file=sys.stderr)


def _pythonw() -> str:
    """תמיד הפייתון של ה-.venv של הפרויקט (שם מותקנות הספריות), בלי קשר למי שהפעיל את המפעיל."""
    for candidate in (ROOT / ".venv" / "Scripts" / "pythonw.exe", ROOT / ".venv" / "bin" / "python"):
        if candidate.exists():
            return str(candidate)
    exe = Path(sys.executable)
    candidate = exe.with_name("pythonw.exe")
    return str(candidate if candidate.exists() else exe)


def _start_server() -> subprocess.Popen:
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(  # noqa: S603 - מריץ את הקובץ של הפרויקט עצמו
        [_pythonw(), str(ROOT / "backend" / "run.py"), "--windowless"],
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
        close_fds=True,
    )


def main() -> None:
    try:
        _main()
    except Exception:  # noqa: BLE001 - אין חלון, אז מציגים ושומרים את השגיאה
        log = ROOT / "data" / "launcher.log"
        log.parent.mkdir(exist_ok=True)
        log.write_text(traceback.format_exc(), encoding="utf-8")
        _message(f"שגיאה בהפעלת DayPilot.\n\nפרטים בקובץ:\n{log}")


def _main() -> None:
    background = "--background" in sys.argv
    url = f"http://127.0.0.1:{_port()}"

    if not (ROOT / "frontend" / "dist" / "index.html").exists():
        _message("הממשק עוד לא נבנה.\n\nיש להריץ פעם אחת בתיקייה frontend:\nnpm run build")
        return

    if not _is_up(url):
        proc = _start_server()
        deadline = time.monotonic() + STARTUP_TIMEOUT_S
        while not _is_up(url):
            if proc.poll() is not None:
                _message(f"השרת נעצר מיד אחרי ההפעלה.\n\nפרטים בקובץ:\n{ROOT / 'data' / 'server.log'}")
                return
            if time.monotonic() > deadline:
                _message(f"השרת לא עלה תוך {STARTUP_TIMEOUT_S} שניות.\n\nפרטים בקובץ:\n{ROOT / 'data' / 'server.log'}")
                return
            time.sleep(0.5)

    if not background:
        webbrowser.open(url)


if __name__ == "__main__":
    main()

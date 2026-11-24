"""
יוצר קיצור דרך "DayPilot" בשולחן העבודה (Windows).

הרצה פעם אחת, מתיקיית הפרויקט, עם ה-.venv פעיל:
    python make_shortcut.py              # אייקון בשולחן העבודה
    python make_shortcut.py --autostart  # בנוסף: השרת עולה לבד בכניסה ל-Windows (בלי לפתוח דפדפן)
    python make_shortcut.py --remove-autostart

הקיצור מריץ את DayPilot.pyw עם pythonw.exe של ה-.venv, כך שלא נפתח חלון CMD.
הקיצור נוצר דרך PowerShell (WScript.Shell), בלי ספריות נוספות.
"""

from __future__ import annotations

import base64
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAME = "DayPilot"


def _ps(script: str) -> str:
    # EncodedCommand (UTF-16LE) כדי שנתיבים בעברית יעברו בלי בעיות קידוד
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    result = subprocess.run(  # noqa: S603, S607
        ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        capture_output=True,
        check=False,
    )
    out = result.stdout.decode("utf-8", errors="replace").strip()
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip() or "PowerShell failed")
    return out


def _q(value: str | Path) -> str:
    """מחרוזת PowerShell בגרש בודד."""
    return "'" + str(value).replace("'", "''") + "'"


def _folder(name: str) -> Path:
    return Path(_ps(f"[Console]::OutputEncoding=[Text.Encoding]::UTF8; [Environment]::GetFolderPath('{name}')"))


def _pythonw() -> Path:
    """הקיצור מפעיל תמיד את הפייתון של ה-.venv, גם אם הסקריפט הורץ בלי ה-.venv פעיל."""
    exe = ROOT / ".venv" / "Scripts" / "pythonw.exe"
    if not exe.exists():
        sys.exit(f"לא נמצא {exe}. יש ליצור את ה-.venv של הפרויקט קודם.")
    return exe


def _icon() -> Path:
    """האייקון שמור כטקסט (base64) ב-assets, ונכתב לקובץ .ico בהרצה."""
    ico = ROOT / "assets" / "daypilot.ico"
    ico.write_bytes(base64.b64decode((ROOT / "assets" / "daypilot.ico.b64").read_text(encoding="ascii")))
    return ico


def _create(link: Path, args: str) -> None:
    script = "\n".join([
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut(" + _q(link) + ")",
        "$s.TargetPath = " + _q(_pythonw()),
        "$s.Arguments = " + _q(args),
        "$s.WorkingDirectory = " + _q(ROOT),
        "$s.IconLocation = " + _q(str(_icon()) + ",0"),
        "$s.Description = 'DayPilot'",
        "$s.Save()",
    ])
    _ps(script)


def main() -> None:
    if sys.platform != "win32":
        sys.exit("הסקריפט מיועד ל-Windows.")
    launcher = ROOT / "DayPilot.pyw"
    startup = _folder("Startup") / f"{NAME}.lnk"

    if "--remove-autostart" in sys.argv:
        if startup.exists():
            startup.unlink()
            print("ההפעלה האוטומטית בוטלה.")
        else:
            print("לא הייתה הפעלה אוטומטית.")
        return

    if not (ROOT / "frontend" / "dist" / "index.html").exists():
        print("שימי לב: הממשק עוד לא נבנה. יש להריץ בתיקייה frontend: npm run build")

    desktop = _folder("Desktop") / f"{NAME}.lnk"
    _create(desktop, f'"{launcher}"')
    print(f"נוצר קיצור דרך: {desktop}")

    if "--autostart" in sys.argv:
        _create(startup, f'"{launcher}" --background')
        print(f"הפעלה אוטומטית עם Windows: {startup}")


if __name__ == "__main__":
    main()

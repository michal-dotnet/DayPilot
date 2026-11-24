"""
בדיקת חיבור ל-OpenAI ול-LangSmith בלי עלות (רשימת מודלים ופרויקטים לא צורכת טוקנים).

הרצה מתיקיית הפרויקט:
    python backend/check_openai.py

מדפיס: האם המפתח נטען (רק 4 התווים האחרונים), האם השרת נגיש, והאם המודל שבהגדרות קיים.
"""

import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from daypilot.config import get_settings  # noqa: E402
from daypilot.utils.tls import use_system_certificates  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def chain(exc: BaseException) -> str:
    parts, seen = [], set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        parts.append(f"  {type(exc).__name__}: {str(exc)[:300]}")
        exc = exc.__cause__ or exc.__context__
    return "\n".join(parts)


def main() -> None:
    settings = get_settings()
    system_certs = use_system_certificates(settings.use_system_certificates)
    print(f"0. אימות תעודות מול מאגר Windows: {'פעיל' if system_certs else 'כבוי'}")
    key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else ""
    print(f"1. מפתח: {'נטען, מסתיים ב-...' + key[-4:] if len(key) > 8 else 'חסר או קצר מדי'}")
    print(f"   מודל בהגדרות: {settings.model_name}")

    try:
        ip = socket.gethostbyname("api.openai.com")
        print(f"2. DNS: api.openai.com -> {ip}")
    except OSError as exc:
        print(f"2. DNS נכשל: {exc}  (אין אינטרנט, או שהכתובת חסומה ברשת)")
        return

    try:
        with socket.create_connection(("api.openai.com", 443), timeout=10):
            print("3. חיבור לפורט 443: הצליח")
    except OSError as exc:
        print(f"3. חיבור לפורט 443 נכשל: {exc}  (חומת אש, אנטי-וירוס או סינון רשת)")
        return

    from openai import OpenAI

    try:
        client = OpenAI(api_key=key, timeout=20, max_retries=0)
        ids = {m.id for m in client.models.list().data}
        print(f"4. גישה ל-API: הצליחה ({len(ids)} מודלים זמינים)")
        print(f"5. המודל {settings.model_name}: {'קיים' if settings.model_name in ids else 'לא נמצא ברשימה!'}")
    except Exception as exc:  # כאן רוצים לראות כל סוג שגיאה
        print("4. גישה ל-API נכשלה:")
        print(chain(exc))


def check_langsmith() -> None:
    settings = get_settings()
    key = settings.langsmith_api_key.get_secret_value() if settings.langsmith_api_key else ""
    print(f"6. מפתח LangSmith: {'נטען, מסתיים ב-...' + key[-4:] if len(key) > 8 else 'חסר'}"
          f"; Tracing: {'פעיל' if settings.langsmith_tracing else 'כבוי'}; פרויקט: {settings.langsmith_project}")
    if not key:
        return
    try:
        from langsmith import Client

        client = Client(api_key=key)
        datasets = list(client.list_datasets(limit=5))
        print(f"7. גישה ל-LangSmith: הצליחה (נמצאו {len(datasets)} Datasets)")
    except Exception as exc:  # כאן רוצים לראות כל סוג שגיאה
        print("7. גישה ל-LangSmith נכשלה:")
        print(chain(exc))


if __name__ == "__main__":
    main()
    check_langsmith()

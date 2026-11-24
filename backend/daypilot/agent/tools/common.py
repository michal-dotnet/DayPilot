"""עזרים משותפים לכלים: תשובות JSON קצרות וטיפול אחיד בשגיאות."""

from __future__ import annotations

import json
from datetime import datetime
from functools import wraps

from pydantic import ValidationError as PydanticValidationError

from daypilot.agent.dates import DateParseError
from daypilot.services.errors import DayPilotError
from daypilot.utils.clock import to_local


def dumps(data) -> str:
    return json.dumps(data, ensure_ascii=False, default=_default)


def _default(value):
    if isinstance(value, datetime):
        return to_local(value).strftime("%Y-%m-%dT%H:%M")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return str(value)


def error(message: str, **details) -> str:
    return dumps({"ok": False, "error": message, **details})


def safe_tool(fn):
    """שגיאה צפויה חוזרת למודל כטקסט שהוא יכול לתקן, במקום להפיל את הגרף."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except DayPilotError as exc:
            return error(exc.message, code=exc.code, **exc.details)
        except PydanticValidationError as exc:
            problems = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
            return error("invalid input", problems=problems)
        except DateParseError as exc:
            return error(str(exc), code="bad_date")

    return wrapper

"""
לוגים עם הסתרת סודות.

מסנן שמחליף כל מחרוזת שנראית כמו מפתח API ב-"***".
"""

import logging
import re

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),  # OpenAI
    re.compile(r"lsv2_[A-Za-z0-9_\-]{8,}"),  # LangSmith
    re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)\S+"),
]


def redact(text: str) -> str:
    for pattern in _SECRET_PATTERNS:
        if pattern.groups:
            text = pattern.sub(lambda m: m.group(1) + "***", text)
        else:
            text = pattern.sub("***", text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        record.msg = redact(message)
        record.args = ()
        return True


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(RedactingFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # לוגים של ספריות רשת ו-Alembic רועשים מדי לשימוש רגיל
    for name in ("httpx", "httpx2", "httpcore", "httpcore2", "openai", "alembic"):
        logging.getLogger(name).setLevel(logging.WARNING)

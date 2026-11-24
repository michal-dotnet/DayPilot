"""
חיבור למסד.

SQLite במצב WAL, כדי שתהליך התזכורות והשרת יוכלו לעבוד במקביל.
foreign_keys מופעל, כי SQLite לא אוכף אותם כברירת מחדל.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from daypilot.db.base import Base


def make_engine(url: str) -> Engine:
    is_sqlite = url.startswith("sqlite")
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False} if is_sqlite else {},
        future=True,
    )
    if is_sqlite:

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - פשוט
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            if ":memory:" not in url:
                cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def create_schema(engine: Engine) -> None:
    """יוצר את הטבלאות. בפיתוח שוטף השינויים מנוהלים ב-Alembic."""
    from daypilot.db import models  # noqa: F401  רישום הטבלאות

    Base.metadata.create_all(engine)


def migrate(engine: Engine) -> None:
    """מעדכן את מבנה המסד לגרסה האחרונה (Alembic). בלי קבצי מיגרציה: יוצר טבלאות ישירות."""
    from pathlib import Path

    from daypilot.config import PROJECT_ROOT

    versions = Path(PROJECT_ROOT, "backend", "migrations", "versions")
    if not any(versions.glob("*.py")):
        create_schema(engine)
        return
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", engine.url.render_as_string(hide_password=False).replace("%", "%%"))
    command.upgrade(cfg, "head")


@contextmanager
def unit_of_work(factory: sessionmaker[Session]) -> Iterator[Session]:
    """טרנזקציה אחת: commit בהצלחה, rollback בשגיאה."""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

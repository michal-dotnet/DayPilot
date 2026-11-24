"""סביבת Alembic: משתמשת באותן הגדרות ובאותן טבלאות כמו האפליקציה."""

import sys
from pathlib import Path

# backend/ נכנס ל-sys.path לפי מיקום הקובץ (נתיב הפרויקט כולל רווחים, ולכן לא דרך alembic.ini)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alembic import context  # noqa: E402
from sqlalchemy import engine_from_config, pool  # noqa: E402

from daypilot.config import get_settings  # noqa: E402
from daypilot.db import models  # noqa: E402,F401  רישום הטבלאות
from daypilot.db.base import Base  # noqa: E402

config = context.config
if not config.get_main_option("sqlalchemy.url"):
    settings = get_settings()
    settings.ensure_dirs()
    config.set_main_option("sqlalchemy.url", settings.app_database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,  # SQLite לא תומך ב-ALTER מלא
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

"""
הגדרות המערכת.

כל ההגדרות נקראות ממשתני סביבה ומקובץ .env בשורש הפרויקט.
מפתחות נשמרים כ-SecretStr כדי שלא יודפסו בטעות ללוגים.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/daypilot/config.py -> שורש הפרויקט נמצא שתי תיקיות למעלה מ-backend
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # OpenAI
    openai_api_key: SecretStr | None = None
    model_name: str = "gpt-6-luna"
    llm_timeout_s: float = 60.0
    llm_max_retries: int = 2

    # LangSmith
    langsmith_api_key: SecretStr | None = None
    langsmith_tracing: bool = False
    langsmith_project: str = "daypilot"

    # אחסון
    data_dir: Path = PROJECT_ROOT / "data"
    database_url: str | None = None  # ברירת מחדל: SQLite בתוך data_dir

    # יומן ותכנון
    timezone: str = "Asia/Jerusalem"
    slot_minutes: int = 30
    planning_horizon_days: int = 28
    scheduler_time_limit_s: float = 5.0

    # אימות HTTPS מול מאגר התעודות של Windows (נדרש ברשתות עם סינון)
    use_system_certificates: bool = True

    # שרת
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    @property
    def app_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'daypilot.db').as_posix()}"

    @property
    def checkpoint_db_path(self) -> Path:
        return self.data_dir / "checkpoints.db"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    def export_tracing_env(self) -> None:
        """LangSmith קורא את ההגדרות ממשתני סביבה, ולכן מעבירים אליהם את מה שנטען מ-.env."""
        import os

        if self.langsmith_api_key and self.langsmith_tracing:
            os.environ["LANGSMITH_API_KEY"] = self.langsmith_api_key.get_secret_value()
            os.environ["LANGSMITH_TRACING"] = "true"
            os.environ["LANGSMITH_PROJECT"] = self.langsmith_project
        else:
            os.environ["LANGSMITH_TRACING"] = "false"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()

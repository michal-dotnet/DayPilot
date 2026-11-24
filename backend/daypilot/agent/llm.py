"""
יצירת המודל במקום אחד.

המפתח נקרא מההגדרות (.env) ולא מופיע בקוד.
המודל gpt-6-luna לא תומך ב-temperature מותאם, ולכן לא מעבירים אותו (כמו בפרויקט המורה).
"""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from daypilot.config import Settings


class MissingApiKeyError(RuntimeError):
    pass


def build_llm(settings: Settings) -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else ""
    if not key or key.startswith("sk-...") or key == "test-key":
        raise MissingApiKeyError(
            "OPENAI_API_KEY חסר או לא תקין. העתיקו את .env.example ל-.env והכניסו את המפתח."
        )
    return ChatOpenAI(
        model=settings.model_name,
        api_key=key,
        timeout=settings.llm_timeout_s,
        max_retries=settings.llm_max_retries,
    )

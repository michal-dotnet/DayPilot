"""
אימות תעודות HTTPS מול מאגר התעודות של מערכת ההפעלה.

ברשתות עם סינון שבודק תעבורה מוצפנת, הסינון מציג תעודה משלו שמותקנת ב-Windows.
Python 3.13 בודק תעודות בצורה מחמירה ודוחה חלק מהן ("CA cert does not include key usage extension").
truststore גורם ל-Python לאמת מול מאגר מערכת ההפעלה, כמו הדפדפן.
האימות נשאר פעיל: לא מבטלים בדיקת תעודות בשום מצב.
"""

import logging

log = logging.getLogger(__name__)
_done = False


def use_system_certificates(enabled: bool = True) -> bool:
    global _done
    if _done or not enabled:
        return _done
    try:
        import truststore
    except ImportError:
        log.warning("truststore is not installed; using Python's default certificate store")
        return False
    truststore.inject_into_ssl()
    _done = True
    return True

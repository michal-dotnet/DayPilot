"""ערכים קבועים של התחום. StrEnum כדי שיישמרו כטקסט קריא במסד וב-JSON."""

from enum import StrEnum


class TaskType(StrEnum):
    SCHEDULED = "scheduled"  # יש מועד יעד ומשך עבודה נדרש
    OPEN = "open"  # בלי מועד יעד, רק תזכורות
    RECURRING = "recurring"  # חוזרת: יומית / שבועית / חודשית


class TaskStatus(StrEnum):
    ACTIVE = "active"
    DONE = "done"
    CANCELLED = "cancelled"


class SessionStatus(StrEnum):
    PLANNED = "planned"
    DONE = "done"
    PARTIAL = "partial"
    MISSED = "missed"
    CANCELLED = "cancelled"


class AvailabilityKind(StrEnum):
    ACTIVE_HOURS = "active_hours"  # שעות שבהן אפשר לשבץ בכלל
    PREFERRED_STUDY = "preferred_study"  # שעות מועדפות ללמידה
    CLASS = "class"  # שעות לימודים קבועות (תפוס)
    WORK = "work"  # עבודה (תפוס)
    COMMITMENT = "commitment"  # התחייבות קבועה אחרת (תפוס)

    @property
    def is_busy(self) -> bool:
        return self in (AvailabilityKind.CLASS, AvailabilityKind.WORK, AvailabilityKind.COMMITMENT)


class ExceptionKind(StrEnum):
    BLOCKED = "blocked"  # לא פנויה (יום שלם או חלון)
    EXTRA_AVAILABLE = "extra_available"  # פנויה מעבר לרגיל


class ConflictKind(StrEnum):
    OVERLAP = "overlap"  # מפגש שנופל על זמן תפוס
    CAPACITY = "capacity"  # אין מספיק זמן לפני מועד היעד
    OVERLOAD = "overload"  # יום שעובר את תקרת השעות


class ProposalKind(StrEnum):
    SCHEDULE = "schedule"  # שיבוץ משימות (חדשות או כולן)
    RESCHEDULE = "reschedule"  # שינוי ידני של תוכנית
    DEADLINE_CHANGE = "deadline_change"
    DURATION_CHANGE = "duration_change"
    DELETE_TASK = "delete_task"


class ProposalStatus(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISED = "revised"
    STALE = "stale"  # הנתונים השתנו מאז שההצעה חושבה


class NotificationKind(StrEnum):
    DEADLINE_SOON = "deadline_soon"
    SESSION_SOON = "session_soon"
    OPEN_TASK_IDLE = "open_task_idle"
    POSTPONED_OFTEN = "postponed_often"
    NO_PROGRESS = "no_progress"
    OVERLOAD = "overload"
    DIGEST = "digest"

"""
זיהוי התנגשויות.

שלושה סוגים, כל אחד עם סיבה מובנית שהמודל מנסח בעברית:
- OVERLAP: מפגש קיים שנופל על זמן תפוס (התחייבות, חסימה, שבת) או על מפגש אחר.
- CAPACITY: אין מספיק זמן פנוי לפני מועד היעד.
- OVERLOAD: יום שבו סך העבודה קרוב לתקרה או עובר אותה.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from daypilot.domain.enums import ConflictKind
from daypilot.domain.intervals import Interval
from daypilot.scheduling.types import ExistingSession, PlannedSession, Shortfall
from daypilot.utils.clock import to_local


@dataclass(frozen=True)
class Conflict:
    kind: ConflictKind
    task_ids: tuple[int, ...]
    message: str  # הסבר קצר במבנה קבוע, לשימוש המודל
    details: dict = field(default_factory=dict, hash=False, compare=False)


def find_overlaps(
    sessions: list[ExistingSession],
    busy: list[Interval],
    busy_labels: dict[Interval, str] | None = None,
) -> list[Conflict]:
    conflicts: list[Conflict] = []
    for s in sessions:
        for b in busy:
            if s.interval.overlaps(b):
                label = (busy_labels or {}).get(b, "busy time")
                conflicts.append(
                    Conflict(
                        ConflictKind.OVERLAP,
                        (s.task_id,),
                        f"session overlaps {label}",
                        {"session_id": s.session_id, "start": s.start.isoformat(), "end": s.end.isoformat(), "with": label},
                    )
                )
                break
    ordered = sorted(sessions, key=lambda s: s.start)
    for a, b in zip(ordered, ordered[1:]):
        if a.interval.overlaps(b.interval):
            conflicts.append(
                Conflict(
                    ConflictKind.OVERLAP,
                    (a.task_id, b.task_id),
                    "two sessions overlap",
                    {"first": a.session_id, "second": b.session_id},
                )
            )
    return conflicts


def capacity_conflicts(shortfalls: list[Shortfall]) -> list[Conflict]:
    return [
        Conflict(
            ConflictKind.CAPACITY,
            (s.task_id,),
            f"missing {s.missing_minutes} minutes before deadline",
            {"required_minutes": s.required_minutes, "scheduled_minutes": s.scheduled_minutes, "missing_minutes": s.missing_minutes},
        )
        for s in shortfalls
        if s.missing_minutes > 0
    ]


def overload_conflicts(
    sessions: list[PlannedSession] | list[ExistingSession],
    daily_max_minutes: int,
    tz_name: str,
    threshold: float = 0.9,
) -> list[Conflict]:
    per_day: dict[str, int] = defaultdict(int)
    tasks_per_day: dict[str, set[int]] = defaultdict(set)
    for s in sessions:
        day = to_local(s.start, tz_name).date().isoformat()
        per_day[day] += int((s.end - s.start).total_seconds() // 60)
        tasks_per_day[day].add(s.task_id)
    limit = int(daily_max_minutes * threshold)
    return [
        Conflict(
            ConflictKind.OVERLOAD,
            tuple(sorted(tasks_per_day[day])),
            f"{minutes} minutes planned on {day} (limit {daily_max_minutes})",
            {"day": day, "minutes": minutes, "limit": daily_max_minutes},
        )
        for day, minutes in sorted(per_day.items())
        if minutes >= limit
    ]

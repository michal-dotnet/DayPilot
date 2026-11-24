"""
פעולות על קטעי זמן.

Interval הוא חצי-פתוח: [start, end). כל הזמנים aware.
הפונקציות טהורות ומחזירות רשימות ממוינות וממוזגות.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable


@dataclass(frozen=True, order=True)
class Interval:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("Interval requires aware datetimes")
        if self.end < self.start:
            raise ValueError(f"Interval end {self.end} is before start {self.start}")

    @property
    def duration(self) -> timedelta:
        return self.end - self.start

    @property
    def minutes(self) -> int:
        return int(self.duration.total_seconds() // 60)

    def overlaps(self, other: Interval) -> bool:
        return self.start < other.end and other.start < self.end

    def contains(self, other: Interval) -> bool:
        return self.start <= other.start and other.end <= self.end


def normalize(intervals: Iterable[Interval]) -> list[Interval]:
    """ממיין, מוחק ריקים וממזג קטעים חופפים או צמודים."""
    items = sorted(i for i in intervals if i.end > i.start)
    merged: list[Interval] = []
    for item in items:
        if merged and item.start <= merged[-1].end:
            last = merged[-1]
            merged[-1] = Interval(last.start, max(last.end, item.end))
        else:
            merged.append(item)
    return merged


def subtract(base: Iterable[Interval], remove: Iterable[Interval]) -> list[Interval]:
    """base פחות remove."""
    result: list[Interval] = []
    cuts = normalize(remove)
    for piece in normalize(base):
        current = [piece]
        for cut in cuts:
            if cut.start >= piece.end:
                break
            next_round: list[Interval] = []
            for part in current:
                if not part.overlaps(cut):
                    next_round.append(part)
                    continue
                if part.start < cut.start:
                    next_round.append(Interval(part.start, cut.start))
                if cut.end < part.end:
                    next_round.append(Interval(cut.end, part.end))
            current = next_round
        result.extend(current)
    return normalize(result)


def intersect(a: Iterable[Interval], b: Iterable[Interval]) -> list[Interval]:
    a_list, b_list = normalize(a), normalize(b)
    result: list[Interval] = []
    i = j = 0
    while i < len(a_list) and j < len(b_list):
        start = max(a_list[i].start, b_list[j].start)
        end = min(a_list[i].end, b_list[j].end)
        if start < end:
            result.append(Interval(start, end))
        if a_list[i].end < b_list[j].end:
            i += 1
        else:
            j += 1
    return result


def total_minutes(intervals: Iterable[Interval]) -> int:
    return sum(i.minutes for i in normalize(intervals))

"""גישה למשימות, מפגשים, יומן התקדמות וגרסאות תוכנית."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from daypilot.db.models import PlanVersion, ProgressLog, ScheduledSession, Task
from daypilot.domain.enums import SessionStatus, TaskStatus, TaskType


class TaskRepository:
    def __init__(self, session: Session):
        self.s = session

    def get(self, user_id: int, task_id: int) -> Task | None:
        task = self.s.get(Task, task_id)
        return task if task and task.user_id == user_id else None

    def add(self, task: Task) -> Task:
        self.s.add(task)
        self.s.flush()
        return task

    def delete(self, task: Task) -> None:
        self.s.delete(task)
        self.s.flush()

    def list(
        self,
        user_id: int,
        statuses: Iterable[TaskStatus] | None = (TaskStatus.ACTIVE,),
        types: Iterable[TaskType] | None = None,
    ) -> list[Task]:
        q = select(Task).where(Task.user_id == user_id)
        if statuses:
            q = q.where(Task.status.in_(list(statuses)))
        if types:
            q = q.where(Task.task_type.in_(list(types)))
        return list(self.s.scalars(q.order_by(Task.deadline.is_(None), Task.deadline, Task.id)))

    def find_by_title(self, user_id: int, text: str) -> list[Task]:
        pattern = f"%{text.strip()}%"
        return list(
            self.s.scalars(
                select(Task).where(Task.user_id == user_id, Task.title.like(pattern), Task.status == TaskStatus.ACTIVE)
            )
        )


class SessionRepository:
    def __init__(self, session: Session):
        self.s = session

    def get(self, user_id: int, session_id: int) -> ScheduledSession | None:
        item = self.s.get(ScheduledSession, session_id)
        return item if item and item.user_id == user_id else None

    def in_range(
        self,
        user_id: int,
        start: datetime,
        end: datetime,
        statuses: Iterable[SessionStatus] | None = None,
    ) -> list[ScheduledSession]:
        q = select(ScheduledSession).where(
            ScheduledSession.user_id == user_id,
            ScheduledSession.start < end,
            ScheduledSession.end > start,
        )
        if statuses:
            q = q.where(ScheduledSession.status.in_(list(statuses)))
        return list(self.s.scalars(q.order_by(ScheduledSession.start)))

    def for_task(self, user_id: int, task_id: int) -> list[ScheduledSession]:
        return list(
            self.s.scalars(
                select(ScheduledSession)
                .where(ScheduledSession.user_id == user_id, ScheduledSession.task_id == task_id)
                .order_by(ScheduledSession.start)
            )
        )

    def add_many(self, items: list[ScheduledSession]) -> None:
        self.s.add_all(items)
        self.s.flush()

    def delete_ids(self, user_id: int, ids: Iterable[int]) -> int:
        ids = list(ids)
        if not ids:
            return 0
        result = self.s.execute(
            delete(ScheduledSession).where(ScheduledSession.user_id == user_id, ScheduledSession.id.in_(ids))
        )
        return result.rowcount

    def add_plan_version(self, user_id: int, reason: str, proposal_id: str | None, now: datetime) -> PlanVersion:
        version = PlanVersion(user_id=user_id, reason=reason, proposal_id=proposal_id, created_at=now)
        self.s.add(version)
        self.s.flush()
        return version

    def plan_version_for_proposal(self, user_id: int, proposal_id: str) -> PlanVersion | None:
        return self.s.scalars(
            select(PlanVersion).where(PlanVersion.user_id == user_id, PlanVersion.proposal_id == proposal_id)
        ).first()


class ProgressRepository:
    def __init__(self, session: Session):
        self.s = session

    def add(self, log: ProgressLog) -> ProgressLog:
        self.s.add(log)
        self.s.flush()
        return log

    def for_range(self, user_id: int, start: datetime, end: datetime) -> list[ProgressLog]:
        return list(
            self.s.scalars(
                select(ProgressLog)
                .where(ProgressLog.user_id == user_id, ProgressLog.logged_at >= start, ProgressLog.logged_at < end)
                .order_by(ProgressLog.logged_at)
            )
        )

    def for_task(self, user_id: int, task_id: int) -> list[ProgressLog]:
        return list(
            self.s.scalars(
                select(ProgressLog)
                .where(ProgressLog.user_id == user_id, ProgressLog.task_id == task_id)
                .order_by(ProgressLog.logged_at)
            )
        )

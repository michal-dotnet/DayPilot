"""
לוגיקה עסקית של משימות.

כאן נמצאות רק פעולות שהמדיניות מאפשרת לבצע אוטומטית:
יצירה, עדכון פרטים פשוטים, דיווח התקדמות וסימון כהושלמה.
שינויים שמשפיעים על הלוח (מועד, משך, מחיקה) מתבצעים רק דרך הצעה מאושרת,
ב-ScheduleService.apply_proposal.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from daypilot.db.models import ProgressLog, Task
from daypilot.db.repositories.tasks import ProgressRepository, SessionRepository, TaskRepository
from daypilot.domain.enums import SessionStatus, TaskStatus, TaskType
from daypilot.domain.schemas import ProgressReport, TaskCreate, TaskDetailsUpdate, TaskView
from daypilot.services.errors import NotFoundError, ValidationError
from daypilot.utils.clock import Clock


class TaskService:
    def __init__(self, session: Session, clock: Clock):
        self.s = session
        self.clock = clock
        self.tasks = TaskRepository(session)
        self.sessions = SessionRepository(session)
        self.progress = ProgressRepository(session)

    # ---------- יצירה ושליפה ----------

    def create(self, user_id: int, data: TaskCreate) -> Task:
        now = self.clock.now()
        if data.task_type == TaskType.SCHEDULED and data.deadline is not None and data.deadline <= now:
            raise ValidationError("deadline is in the past", deadline=data.deadline.isoformat())
        task = Task(
            user_id=user_id,
            title=data.title,
            description=data.description,
            task_type=data.task_type,
            status=TaskStatus.ACTIVE,
            importance=data.importance,
            deadline=data.deadline,
            estimated_minutes=data.estimated_minutes,
            remaining_minutes=data.estimated_minutes,
            recurrence_rule=data.recurrence_rule,
            recurrence_start=data.recurrence_start or now.date(),
            recurrence_end=data.recurrence_end,
            occurrence_time=data.occurrence_time,
            occurrence_minutes=data.occurrence_minutes,
            prep_minutes=data.prep_minutes,
            assumptions=list(data.assumptions),
            created_at=now,
            updated_at=now,
        )
        return self.tasks.add(task)

    def get(self, user_id: int, task_id: int) -> Task:
        task = self.tasks.get(user_id, task_id)
        if task is None:
            raise NotFoundError(f"task {task_id} not found", task_id=task_id)
        return task

    def list(self, user_id: int, include_done: bool = False) -> list[Task]:
        statuses = None if include_done else (TaskStatus.ACTIVE,)
        return self.tasks.list(user_id, statuses=statuses)

    def view(self, task: Task) -> TaskView:
        sessions = self.sessions.for_task(task.user_id, task.id)
        now = self.clock.now()
        scheduled = sum(
            int((x.end - x.start).total_seconds() // 60)
            for x in sessions
            if x.status == SessionStatus.PLANNED and x.end > now
        )
        done = sum(log.minutes for log in self.progress.for_task(task.user_id, task.id))
        return TaskView(
            id=task.id,
            title=task.title,
            task_type=task.task_type,
            status=task.status,
            importance=task.importance,
            deadline=task.deadline,
            estimated_minutes=task.estimated_minutes,
            remaining_minutes=task.remaining_minutes,
            scheduled_minutes=scheduled,
            done_minutes=done,
            postponed_count=task.postponed_count,
            recurrence_rule=task.recurrence_rule,
            assumptions=list(task.assumptions or []),
        )

    # ---------- עדכונים אוטומטיים ----------

    def update_details(self, user_id: int, task_id: int, data: TaskDetailsUpdate) -> Task:
        task = self.get(user_id, task_id)
        changes = data.model_dump(exclude_none=True)
        if not changes:
            raise ValidationError("nothing to update")
        for key, value in changes.items():
            setattr(task, key, value)
        task.updated_at = self.clock.now()
        return task

    def log_progress(self, user_id: int, report: ProgressReport) -> Task:
        task = self.get(user_id, report.task_id)
        if task.status != TaskStatus.ACTIVE:
            raise ValidationError("task is not active", status=task.status)
        now = self.clock.now()
        session_row = None
        if report.session_id is not None:
            session_row = self.sessions.get(user_id, report.session_id)
            if session_row is None or session_row.task_id != task.id:
                raise NotFoundError("session not found for this task", session_id=report.session_id)
            planned = int((session_row.end - session_row.start).total_seconds() // 60)
            session_row.actual_minutes = report.minutes
            session_row.status = SessionStatus.DONE if report.minutes >= planned else SessionStatus.PARTIAL
            session_row.locked = True

        self.progress.add(
            ProgressLog(
                user_id=user_id,
                task_id=task.id,
                session_id=session_row.id if session_row else None,
                minutes=report.minutes,
                note=report.note,
                logged_at=now,
            )
        )
        if task.remaining_minutes is not None:
            task.remaining_minutes = max(0, task.remaining_minutes - report.minutes)
        task.last_progress_at = now
        task.updated_at = now
        if report.completed or (task.task_type == TaskType.SCHEDULED and task.remaining_minutes == 0):
            self._complete(task)
        return task

    def mark_done(self, user_id: int, task_id: int) -> Task:
        task = self.get(user_id, task_id)
        self._complete(task)
        return task

    def _complete(self, task: Task) -> None:
        now = self.clock.now()
        task.status = TaskStatus.DONE
        task.completed_at = now
        task.updated_at = now
        if task.remaining_minutes is not None:
            task.remaining_minutes = 0
        # מפגשים עתידיים של משימה שהושלמה כבר לא נחוצים: מסמנים כמבוטלים ומשחררים זמן
        for row in self.sessions.for_task(task.user_id, task.id):
            if row.status == SessionStatus.PLANNED and row.start >= now:
                row.status = SessionStatus.CANCELLED

    def mark_missed_sessions(self, user_id: int) -> int:
        """מפגשים מתוכננים שהזמן שלהם עבר בלי דיווח הופכים ל'הוחמצו'. מחזיר כמה."""
        now = self.clock.now()
        count = 0
        for task in self.tasks.list(user_id):
            for row in self.sessions.for_task(user_id, task.id):
                if row.status == SessionStatus.PLANNED and row.end <= now:
                    row.status = SessionStatus.MISSED
                    task.postponed_count += 1
                    count += 1
        return count

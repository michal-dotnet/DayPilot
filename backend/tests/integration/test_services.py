"""בדיקות אינטגרציה: Services מול מסד SQLite בזיכרון ומנוע תכנון אמיתי."""

from datetime import time, timedelta

import pytest
from sqlalchemy import func, select

from daypilot.db.models import Proposal, ScheduledSession
from daypilot.domain.enums import (
    AvailabilityKind,
    ConflictKind,
    ProposalKind,
    SessionStatus,
    TaskStatus,
    TaskType,
)
from daypilot.domain.intervals import Interval
from daypilot.domain.schemas import (
    ProgressReport,
    TaskChange,
    TaskCreate,
    TaskDetailsUpdate,
    WeeklyRuleIn,
)
from daypilot.services.errors import StaleProposalError, ValidationError
from daypilot.services.schedule_service import PlanOverrides
from daypilot.services.settings_service import SettingsService
from daypilot.utils.clock import to_local
from tests.conftest import START_DAY, TZ, L


def count_sessions(db) -> int:
    return db.scalar(select(func.count()).select_from(ScheduledSession))


def exam(tasks, user, hours=10, days=5, importance=4, title="מבחן"):
    return tasks.create(
        user.id,
        TaskCreate(
            title=title,
            task_type=TaskType.SCHEDULED,
            deadline=L(START_DAY + timedelta(days=days), 9),
            estimated_minutes=hours * 60,
            importance=importance,
        ),
    )


def test_create_task_rejects_past_deadline(tasks, user):
    with pytest.raises(ValidationError):
        tasks.create(
            user.id,
            TaskCreate(title="x", task_type=TaskType.SCHEDULED, deadline=L(START_DAY, 7), estimated_minutes=60),
        )


def test_scheduled_task_requires_deadline_and_duration():
    with pytest.raises(Exception):
        TaskCreate(title="x", task_type=TaskType.SCHEDULED)


def test_propose_does_not_write_and_apply_does(db, tasks, schedule, user):
    task = exam(tasks, user)
    db.commit()
    proposal = schedule.propose(user.id, ProposalKind.SCHEDULE, "schedule exam", [task.id])
    assert proposal.feasible
    assert sum((s.end - s.start).total_seconds() for s in proposal.add_sessions) == 10 * 3600
    assert count_sessions(db) == 0  # הצעה לא כותבת

    result = schedule.apply_proposal(user.id, proposal, "thread-1")
    db.commit()
    assert result["status"] == "applied"
    assert count_sessions(db) == len(proposal.add_sessions)
    assert db.get(Proposal, proposal.id).status == "approved"

    again = schedule.apply_proposal(user.id, proposal, "thread-1")
    assert again["status"] == "already_applied"
    assert count_sessions(db) == len(proposal.add_sessions)


def test_stale_proposal_is_refused(db, tasks, schedule, user):
    task = exam(tasks, user)
    db.commit()
    proposal = schedule.propose(user.id, ProposalKind.SCHEDULE, "s", [task.id])
    tasks.update_details(user.id, task.id, TaskDetailsUpdate(importance=5))
    db.commit()
    with pytest.raises(StaleProposalError):
        schedule.apply_proposal(user.id, proposal)


def test_replanning_unchanged_state_proposes_nothing(db, tasks, schedule, user):
    task = exam(tasks, user)
    db.commit()
    schedule.apply_proposal(user.id, schedule.propose(user.id, ProposalKind.SCHEDULE, "s", [task.id]))
    db.commit()
    second = schedule.propose(user.id, ProposalKind.SCHEDULE, "again")
    assert second.add_sessions == []
    assert second.remove_session_ids == []


def test_rest_blocks_and_classes_are_respected(db, tasks, schedule, rest, user, clock):
    friday = START_DAY + timedelta(days=5)
    saturday = friday + timedelta(days=1)
    rest.blocks = [Interval(L(friday, 13), L(saturday, 18))]
    settings = SettingsService(db, clock)
    for wd in range(0, 5):
        settings.add_rule(user.id, WeeklyRuleIn(weekday=wd, start_time=time(9), end_time=time(14), kind=AvailabilityKind.CLASS))
    task = exam(tasks, user, hours=20, days=7)
    db.commit()
    proposal = schedule.propose(user.id, ProposalKind.SCHEDULE, "s", [task.id])
    for s in proposal.add_sessions:
        local = to_local(s.start, TZ)
        assert not Interval(s.start, s.end).overlaps(rest.blocks[0])
        if local.weekday() in (6, 0, 1, 2, 3):  # ראשון-חמישי
            assert not (time(9) <= local.time() < time(14))


def test_deadline_change_and_delete_go_through_proposal(db, tasks, schedule, user):
    task = exam(tasks, user, hours=4, days=3)
    db.commit()
    schedule.apply_proposal(user.id, schedule.propose(user.id, ProposalKind.SCHEDULE, "s", [task.id]))
    db.commit()

    new_deadline = L(START_DAY + timedelta(days=6), 9)
    change = schedule.propose(
        user.id, ProposalKind.DEADLINE_CHANGE, "move deadline", [task.id],
        task_changes=[TaskChange(task_id=task.id, deadline=new_deadline)],
    )
    assert tasks.get(user.id, task.id).deadline != new_deadline  # עדיין לא נכתב
    schedule.apply_proposal(user.id, change)
    db.commit()
    assert tasks.get(user.id, task.id).deadline == new_deadline
    assert tasks.get(user.id, task.id).postponed_count == 1

    delete = schedule.propose(
        user.id, ProposalKind.DELETE_TASK, "delete", [task.id], task_changes=[TaskChange(task_id=task.id, delete=True)]
    )
    schedule.apply_proposal(user.id, delete)
    db.commit()
    assert tasks.tasks.get(user.id, task.id) is None
    assert count_sessions(db) == 0


def test_capacity_conflict_with_alternatives(db, tasks, schedule, user):
    task = exam(tasks, user, hours=20, days=2, title="פרויקט")
    db.commit()
    proposal = schedule.propose(user.id, ProposalKind.SCHEDULE, "s", [task.id])
    assert not proposal.feasible
    capacity = [c for c in proposal.conflicts if c.kind == ConflictKind.CAPACITY]
    assert capacity and capacity[0].task_ids == [task.id]
    assert proposal.alternatives, "expected computed alternatives"
    assert all(a.missing_minutes < capacity[0].details["missing_minutes"] for a in proposal.alternatives)


def test_move_all_study_to_one_day(db, tasks, schedule, user):
    task = exam(tasks, user, hours=4, days=5)
    db.commit()
    schedule.apply_proposal(user.id, schedule.propose(user.id, ProposalKind.SCHEDULE, "s", [task.id]))
    db.commit()
    tuesday = START_DAY + timedelta(days=2)
    window = Interval(L(tuesday, 0), L(tuesday + timedelta(days=1), 0))
    proposal = schedule.propose(
        user.id, ProposalKind.RESCHEDULE, "all on Tuesday", [task.id],
        overrides=PlanOverrides(task_windows={task.id: [window]}),
    )
    schedule.apply_proposal(user.id, proposal)
    db.commit()
    rows = [r for r in db.scalars(select(ScheduledSession)) if r.status == SessionStatus.PLANNED]
    assert rows and all(to_local(r.start, TZ).date() == tuesday for r in rows)


def test_recurring_event_blocks_time_and_prep_is_scheduled(db, tasks, schedule, user):
    quiz = tasks.create(
        user.id,
        TaskCreate(
            title="בוחן שבועי", task_type=TaskType.RECURRING, recurrence_rule="FREQ=WEEKLY;BYDAY=WE",
            occurrence_time=time(10), occurrence_minutes=60, prep_minutes=60,
        ),
    )
    db.commit()
    proposal = schedule.propose(user.id, ProposalKind.SCHEDULE, "s")
    wednesday = START_DAY + timedelta(days=3)
    event = Interval(L(wednesday, 10), L(wednesday, 11))
    prep = [s for s in proposal.add_sessions if s.task_id == quiz.id and s.occurrence_date == wednesday]
    assert sum((s.end - s.start).total_seconds() for s in prep) == 3600
    assert all(s.end <= event.start for s in prep)
    assert all(not Interval(s.start, s.end).overlaps(event) for s in proposal.add_sessions)


def test_progress_and_completion(db, tasks, schedule, user):
    task = exam(tasks, user, hours=3, days=3)
    db.commit()
    schedule.apply_proposal(user.id, schedule.propose(user.id, ProposalKind.SCHEDULE, "s", [task.id]))
    db.commit()
    tasks.log_progress(user.id, ProgressReport(task_id=task.id, minutes=60))
    assert tasks.get(user.id, task.id).remaining_minutes == 120
    tasks.log_progress(user.id, ProgressReport(task_id=task.id, minutes=120))
    db.commit()
    done = tasks.get(user.id, task.id)
    assert done.status == TaskStatus.DONE
    assert all(r.status == SessionStatus.CANCELLED for r in db.scalars(select(ScheduledSession)))

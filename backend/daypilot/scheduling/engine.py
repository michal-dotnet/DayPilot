"""
מנוע התכנון: OR-Tools CP-SAT.

המודל:
- x[t, s]  = 1 אם משימה t משובצת במשבצת s.
- start[t, s] = 1 אם במשבצת s מתחיל מפגש רצוף של t.
- short[t] = כמה משבצות חסרות למשימה t (חוסר מדוד במקום כישלון).

אילוצים קשיחים:
- משבצת אחת לכל היותר למשימה.
- עבודה רק לפני מועד היעד (ואחרי earliest_start).
- מפגש רצוף באורך בין המינימום למקסימום.
- תקרת שעות יומית (כולל מפגשים נעולים באותו יום).

מטרה (מינימום):
- חוסר: קנס גבוה מאוד, גדל עם חשיבות המשימה.
- זמן לא מועדף, עבודה מאוחרת יותר באופק, ריבוי מפגשים קצרים, יום עמוס במיוחד.
- הזזת מפגשים קיימים (יציבות התוכנית).
"""

from __future__ import annotations

import math
import time as _time
from collections import defaultdict
from typing import Protocol

from ortools.sat.python import cp_model

from daypilot.scheduling.slots import Slot, build_slots
from daypilot.scheduling.types import PlannedSession, PlanningInput, PlanResult, Shortfall

# משקלי המטרה. נבחרו כך שחוסר תמיד יקר מכל העדפה אחרת.
W_SHORTFALL_BASE = 10_000
W_SHORTFALL_PER_IMPORTANCE = 2_000
W_NOT_PREFERRED = 6
W_DAY_INDEX = 1
W_SESSION_START = 8
W_MOVED_SLOT = 10
W_PEAK_DAY = 4


class Scheduler(Protocol):
    def plan(self, data: PlanningInput) -> PlanResult: ...


class CpSatScheduler:
    def plan(self, data: PlanningInput) -> PlanResult:
        started = _time.perf_counter()
        rules = data.rules
        slot_min = rules.slot_minutes
        slots = build_slots(data.free, data.preferred, slot_min, data.tz_name, first_day_local=data.now)

        tasks = [t for t in data.tasks if t.remaining_minutes > 0]
        if not tasks:
            return PlanResult(status="optimal", sessions=[], shortfalls=[], solve_seconds=0.0)

        required = {t.id: math.ceil(t.remaining_minutes / slot_min) for t in tasks}
        max_len = max(1, rules.max_session_minutes // slot_min)
        base_min_len = max(1, rules.min_session_minutes // slot_min)

        model = cp_model.CpModel()
        x: dict[tuple[int, int], cp_model.IntVar] = {}
        eligible: dict[int, list[Slot]] = {}

        for t in tasks:
            ok = [
                s
                for s in slots
                if s.end <= t.deadline
                and s.start >= data.now
                and (t.earliest_start is None or s.start >= t.earliest_start)
                and (t.allowed is None or any(w.start <= s.start and s.end <= w.end for w in t.allowed))
            ]
            eligible[t.id] = ok
            for s in ok:
                x[t.id, s.index] = model.NewBoolVar(f"x_{t.id}_{s.index}")

        # משבצת אחת לכל היותר
        by_slot: dict[int, list[cp_model.IntVar]] = defaultdict(list)
        for (tid, sidx), var in x.items():
            by_slot[sidx].append(var)
        for vars_ in by_slot.values():
            if len(vars_) > 1:
                model.AddAtMostOne(vars_)

        # כמות נדרשת + חוסר
        short: dict[int, cp_model.IntVar] = {}
        for t in tasks:
            need = required[t.id]
            short[t.id] = model.NewIntVar(0, need, f"short_{t.id}")
            model.Add(sum(x[t.id, s.index] for s in eligible[t.id]) + short[t.id] == need)

        # רציפות ואורך מפגש
        slot_by_index = {s.index: s for s in slots}
        starts: dict[tuple[int, int], cp_model.IntVar] = {}
        for t in tasks:
            min_len = min(base_min_len, required[t.id])
            idxs = {s.index for s in eligible[t.id]}
            for s in eligible[t.id]:
                cur = x[t.id, s.index]
                prev_idx = s.index - 1
                has_prev = s.contiguous_with_prev and prev_idx in idxs
                b = model.NewBoolVar(f"b_{t.id}_{s.index}")
                starts[t.id, s.index] = b
                if has_prev:
                    prev = x[t.id, prev_idx]
                    # b = cur AND NOT prev
                    model.AddBoolOr([cur.Not(), prev, b])
                    model.AddImplication(b, cur)
                    model.AddImplication(b, prev.Not())
                else:
                    model.Add(b == cur)

                # מפגש שמתחיל כאן חייב להימשך לפחות min_len משבצות רצופות
                chain = [s.index]
                k = s.index
                while len(chain) < min_len:
                    nxt = slot_by_index.get(k + 1)
                    if nxt is None or not nxt.contiguous_with_prev or nxt.index not in idxs:
                        break
                    chain.append(nxt.index)
                    k = nxt.index
                if len(chain) < min_len:
                    model.Add(b == 0)
                else:
                    for c in chain[1:]:
                        model.AddImplication(b, x[t.id, c])

            # לא יותר מ-max_len משבצות רצופות
            ordered = sorted(idxs)
            for i in ordered:
                window = [i]
                k = i
                while len(window) <= max_len:
                    nxt = slot_by_index.get(k + 1)
                    if nxt is None or not nxt.contiguous_with_prev or nxt.index not in idxs:
                        break
                    window.append(nxt.index)
                    k = nxt.index
                if len(window) == max_len + 1:
                    model.Add(sum(x[t.id, j] for j in window) <= max_len)

        # תקרה יומית
        day_cap_slots = rules.daily_max_minutes // slot_min
        day_vars: dict[str, list[cp_model.IntVar]] = defaultdict(list)
        for (tid, sidx), var in x.items():
            day_vars[slot_by_index[sidx].day_key].append(var)
        day_loads: list[cp_model.IntVar] = []
        for day, vars_ in day_vars.items():
            locked = data.locked_minutes_by_day.get(day, 0) // slot_min
            cap = max(0, day_cap_slots - locked)
            load = model.NewIntVar(0, len(vars_), f"load_{day}")
            model.Add(load == sum(vars_))
            model.Add(load <= cap)
            day_loads.append(load)

        # יציבות: משבצות שבהן המשימה כבר הייתה משובצת
        previously: set[tuple[int, int]] = set()
        for ps in data.previous_sessions:
            for s in slots:
                if s.start >= ps.start and s.end <= ps.end:
                    previously.add((ps.task_id, s.index))

        # מטרה
        importance = {t.id: t.importance for t in tasks}
        terms = []
        for t in tasks:
            weight = W_SHORTFALL_BASE + W_SHORTFALL_PER_IMPORTANCE * importance[t.id]
            terms.append(weight * short[t.id])
        for (tid, sidx), var in x.items():
            s = slot_by_index[sidx]
            cost = W_DAY_INDEX * s.day_index
            if not s.preferred:
                cost += W_NOT_PREFERRED
            if (tid, sidx) in previously:
                cost -= W_MOVED_SLOT
            if cost:
                terms.append(cost * var)
        for b in starts.values():
            terms.append(W_SESSION_START * b)
        if day_loads:
            peak = model.NewIntVar(0, day_cap_slots, "peak")
            model.AddMaxEquality(peak, day_loads)
            terms.append(W_PEAK_DAY * peak)
        model.Minimize(sum(terms))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = data.time_limit_s
        solver.parameters.num_workers = 8
        code = solver.Solve(model)
        elapsed = _time.perf_counter() - started

        if code not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return PlanResult(
                status="no_solution",
                sessions=[],
                shortfalls=[
                    Shortfall(t.id, required[t.id] * slot_min, 0) for t in tasks
                ],
                solve_seconds=elapsed,
            )

        sessions = _collect_sessions(solver, x, slot_by_index, tasks)
        shortfalls = [
            Shortfall(
                task_id=t.id,
                required_minutes=t.remaining_minutes,
                scheduled_minutes=min(t.remaining_minutes, (required[t.id] - solver.Value(short[t.id])) * slot_min),
            )
            for t in tasks
        ]
        moved = sum(1 for key in previously if key in x and solver.Value(x[key]) == 0) * slot_min
        return PlanResult(
            status="optimal" if code == cp_model.OPTIMAL else "feasible",
            sessions=sessions,
            shortfalls=shortfalls,
            moved_minutes=moved,
            solve_seconds=elapsed,
        )


def _collect_sessions(solver, x, slot_by_index, tasks) -> list[PlannedSession]:
    """מאחד משבצות רצופות של אותה משימה למפגש אחד."""
    sessions: list[PlannedSession] = []
    for t in tasks:
        chosen = sorted(sidx for (tid, sidx) in x if tid == t.id and solver.Value(x[tid, sidx]))
        current_start = current_end = None
        prev_idx = None
        for sidx in chosen:
            s = slot_by_index[sidx]
            if prev_idx is not None and sidx == prev_idx + 1 and s.contiguous_with_prev:
                current_end = s.end
            else:
                if current_start is not None:
                    sessions.append(PlannedSession(t.id, current_start, current_end))
                current_start, current_end = s.start, s.end
            prev_idx = sidx
        if current_start is not None:
            sessions.append(PlannedSession(t.id, current_start, current_end))
    return sorted(sessions, key=lambda p: p.start)

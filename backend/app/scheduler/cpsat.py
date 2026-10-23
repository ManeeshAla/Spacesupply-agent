"""OR-Tools CP-SAT: flexible job-shop with precedence, release times and deadlines."""
from __future__ import annotations

import time

from ortools.sat.python import cp_model

from .heuristics import solve_priority
from .metrics import TARDINESS_WEIGHT
from .problem import Problem, Solution


def solve_cpsat(problem: Problem, time_limit_s: float = 8.0, workers: int = 4, hint: Solution | None = None) -> Solution:
    t0 = time.perf_counter()
    jobs = problem.jobs
    if not jobs:
        return Solution({}, "CPSAT", 0.0, True)
    if hint is None:
        hint = solve_priority(problem)          # warm start: never worse than the best simple rule
    horizon = (sum(j.duration for j in jobs.values()) + max(j.release for j in jobs.values())
               + max((mc.free_at for mc in problem.machines.values()), default=0) + 1)
    model = cp_model.CpModel()
    start, end, tard = {}, {}, {}
    presence: dict[tuple[str, str], cp_model.IntVar] = {}
    per_machine: dict[str, list] = {mid: [] for mid in problem.machines}
    for jid, j in jobs.items():
        s = model.NewIntVar(j.release, horizon, f"s_{jid}")
        e = model.NewIntVar(0, horizon, f"e_{jid}")
        model.Add(e == s + j.duration)
        start[jid], end[jid] = s, e
        lits = []
        for mc in problem.machines_of(j.ws_type):
            lit = model.NewBoolVar(f"p_{jid}_{mc.id}")
            iv = model.NewOptionalIntervalVar(s, j.duration, e, lit, f"i_{jid}_{mc.id}")
            per_machine[mc.id].append(iv)
            model.Add(s >= mc.free_at).OnlyEnforceIf(lit)
            presence[(jid, mc.id)] = lit
            lits.append(lit)
        if not lits:
            raise ValueError(f"No workstation of type {j.ws_type} for {jid}")
        model.AddExactlyOne(lits)
        t = model.NewIntVar(0, horizon, f"t_{jid}")
        model.Add(t >= e - j.deadline)
        tard[jid] = t
    for mid, ivs in per_machine.items():
        if ivs:
            model.AddNoOverlap(ivs)
    for jid, j in jobs.items():
        for p in j.preds:
            if p in jobs:
                model.Add(start[jid] >= end[p])
    makespan = model.NewIntVar(0, horizon, "makespan")
    model.AddMaxEquality(makespan, list(end.values()))
    model.Minimize(TARDINESS_WEIGHT * sum(jobs[j].priority * tard[j] for j in jobs) + makespan)

    for jid, (mid, s, e) in hint.assign.items():
        model.AddHint(start[jid], s)
        for (j2, m2), lit in presence.items():
            if j2 == jid:
                model.AddHint(lit, 1 if m2 == mid else 0)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_workers = workers
    solver.parameters.random_seed = 1
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        sol = hint
        sol.algorithm, sol.note = "CPSAT", "solver found no solution; fell back to priority rule"
        return sol
    assign = {}
    for jid, j in jobs.items():
        mid = next(m2 for (j2, m2), lit in presence.items() if j2 == jid and solver.Value(lit))
        s = solver.Value(start[jid])
        assign[jid] = (mid, s, s + j.duration)
    return Solution(assign, "CPSAT", (time.perf_counter() - t0) * 1000, status == cp_model.OPTIMAL,
                    f"status={solver.StatusName(status)}, bound={solver.BestObjectiveBound():.0f}")

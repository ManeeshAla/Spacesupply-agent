"""Baseline dispatching rules: FCFS and Priority. (non-delay, non-preemptive)"""
from __future__ import annotations

import time
from typing import Callable

from .problem import Job, Problem, Solution


def dispatch(problem: Problem, pick: Callable[[list[tuple[Job, int]]], Job], algorithm: str) -> Solution:
    t0 = time.perf_counter()
    free = {mid: mc.free_at for mid, mc in problem.machines.items()}
    end: dict[str, int] = {}
    assign: dict[str, tuple[str, int, int]] = {}
    pending = dict(problem.jobs)
    by_type: dict[str, list[str]] = {}
    for mid, mc in problem.machines.items():
        by_type.setdefault(mc.ws_type, []).append(mid)
    while pending:
        info: dict[str, tuple[int, int, str]] = {}   # job -> (est, start, machine)
        for jid, job in pending.items():
            if any(p in pending for p in job.preds):
                continue
            est = max([job.release] + [end[p] for p in job.preds if p in end])
            best_m = min(by_type[job.ws_type], key=lambda mid: (max(est, free[mid]), mid))
            info[jid] = (est, max(est, free[best_m]), best_m)
        if not info:
            raise ValueError("Dependency cycle in task graph")
        t_star = min(v[1] for v in info.values())
        cands = [(pending[j], info[j][0]) for j, v in info.items() if v[1] == t_star]
        job = pick(cands)
        est, start, mid = info[job.id]
        assign[job.id] = (mid, start, start + job.duration)
        end[job.id] = start + job.duration
        free[mid] = start + job.duration
        del pending[job.id]
    return Solution(assign, algorithm, (time.perf_counter() - t0) * 1000)


def solve_fcfs(problem: Problem) -> Solution:
    """First-come-first-served: whoever became ready first is served first."""
    return dispatch(problem, lambda c: min(c, key=lambda x: (x[1], x[0].order))[0], "FCFS")


def solve_priority(problem: Problem) -> Solution:
    """Priority rule: highest priority first, ties by earliest deadline."""
    return dispatch(problem, lambda c: min(c, key=lambda x: (-x[0].priority, x[0].deadline, x[0].order))[0], "PRIORITY")

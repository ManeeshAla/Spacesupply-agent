from __future__ import annotations

from .problem import Problem, Solution

TARDINESS_WEIGHT = 10   # objective = 10 * weighted tardiness + makespan


def evaluate(problem: Problem, sol: Solution) -> dict:
    a = sol.assign
    if not a:
        return {"makespan": 0, "tardy_tasks": 0, "total_tardiness": 0, "weighted_tardiness": 0,
                "conflicts": 0, "utilization": 0.0, "objective": 0, "runtime_ms": round(sol.runtime_ms, 1),
                "optimal": sol.optimal, "tasks": 0}
    makespan = max(e for (_, _, e) in a.values())
    tard = {j: max(0, e - problem.jobs[j].deadline) for j, (_, _, e) in a.items()}
    total_t = sum(tard.values())
    weighted = sum(problem.jobs[j].priority * t for j, t in tard.items())
    conflicts = count_conflicts(problem, a)
    busy = sum(e - s for (_, s, e) in a.values())
    util = busy / (len(problem.machines) * makespan) if makespan else 0.0
    return {
        "makespan": makespan,
        "tardy_tasks": sum(1 for t in tard.values() if t > 0),
        "total_tardiness": total_t,
        "weighted_tardiness": weighted,
        "conflicts": conflicts,
        "utilization": round(util, 4),
        "objective": TARDINESS_WEIGHT * weighted + makespan,
        "runtime_ms": round(sol.runtime_ms, 1),
        "optimal": sol.optimal,
        "tasks": len(a),
    }


def count_conflicts(problem: Problem, a: dict) -> int:
    """Count violated constraints: machine overlaps, precedence, release, machine availability, wrong machine type."""
    n = 0
    by_m: dict[str, list[tuple[int, int]]] = {}
    for j, (mc, s, e) in a.items():
        job = problem.jobs[j]
        mach = problem.machines[mc]
        if mach.ws_type != job.ws_type:
            n += 1
        if s < job.release or s < mach.free_at:
            n += 1
        if e - s != job.duration:
            n += 1
        for p in job.preds:
            if p in a and a[p][2] > s:
                n += 1
        by_m.setdefault(mc, []).append((s, e))
    for iv in by_m.values():
        iv.sort()
        for (s1, e1), (s2, e2) in zip(iv, iv[1:]):
            if s2 < e1:
                n += 1
    return n

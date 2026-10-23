"""Benchmark FCFS / Priority / GA / CP-SAT on randomized disruption scenarios.

Usage:  python -m scripts.benchmark [--n 30]
Writes artifacts/benchmark.json (used by the Reports page).
"""
from __future__ import annotations

import argparse
import copy
import json
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import seed  # noqa: E402
from app.config import BENCHMARK_PATH  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.scheduler import build_problem, evaluate, solve  # noqa: E402

ALGOS = ["FCFS", "PRIORITY", "GA", "CPSAT"]


def perturb(base, rng: random.Random):
    """Create a disrupted copy: component delays, workstation outages, deadline pressure."""
    pr = copy.deepcopy(base)
    jobs = list(pr.jobs.values())
    for j in rng.sample(jobs, k=rng.randint(3, 7)):
        extra = rng.randint(12, 72)
        j.release += extra
        j.release_comp = j.release
        j.release_comp_ref = j.release_comp_ref or "CMP-DELAY"
    for mc in rng.sample(list(pr.machines.values()), k=rng.randint(1, 3)):
        mc.free_at += rng.randint(12, 60)
    squeeze = rng.uniform(0.85, 1.0)
    for j in jobs:
        j.deadline = int(j.deadline * squeeze)
    return pr


def campaign(base, copies: int = 3, stagger: int = 30):
    """A production campaign: several vehicles share the same 7 workstations (assembly-line load)."""
    from app.scheduler.problem import Job, Problem
    jobs = {}
    for c in range(copies):
        pre = "" if c == 0 else f"V{c + 1}:"
        for j in base.jobs.values():
            nj = copy.deepcopy(j)
            nj.id = pre + j.id
            nj.preds = [pre + p for p in j.preds]
            nj.release = j.release + c * stagger
            nj.deadline = j.deadline + c * stagger
            nj.order = j.order + c * 1000
            jobs[nj.id] = nj
    names = {k: v.name for k, v in jobs.items()}
    return Problem(now=base.now, jobs=jobs, machines=copy.deepcopy(base.machines),
                   comp_names=base.comp_names, job_names={**base.job_names, **names})


def run(label: str, make, n: int, time_limit: float, rng):
    rows = {a: [] for a in ALGOS}
    for i in range(n):
        pr = make(rng)
        for a in ALGOS:
            kw = {"time_limit_s": time_limit} if a == "CPSAT" else {}
            sol = solve(pr, a, **kw)
            met = evaluate(pr, sol)
            assert met["conflicts"] == 0, (a, i, met)
            rows[a].append(met)
        print(f"[{label}] scenario {i + 1}/{n}", {a: rows[a][-1]["objective"] for a in ALGOS}, flush=True)
    return rows, len(pr.jobs)


def main(n: int = 30, time_limit: float = 6.0):
    db = SessionLocal()
    seed.ensure_seeded(db)
    base = build_problem(db)
    rng = random.Random(2026)
    out = {"objective": "10 x priority-weighted tardiness + makespan (lower is better)", "suites": {}}
    for label, make in (("single_vehicle", lambda r: perturb(base, r)),
                        ("three_vehicle_campaign", lambda r: perturb(campaign(base), r))):
        rows, njobs = run(label, make, n, time_limit, rng)
        out["suites"][label] = summarize(rows, n, njobs, len(base.machines))
    BENCHMARK_PATH.write_text(json.dumps(out, indent=2))
    for label, suite in out["suites"].items():
        print(label, suite["jobs_per_scenario"], "jobs")
        for a, v in suite["algorithms"].items():
            print("  ", a, {k: v[k] for k in ("makespan", "tardy_tasks", "weighted_tardiness", "objective", "runtime_ms", "wins_or_ties_best")})


def summarize(rows, n, njobs, nmachines):
    def agg(a):
        r = rows[a]
        f = lambda k: round(statistics.mean(x[k] for x in r), 2)
        return {"makespan": f("makespan"), "tardy_tasks": f("tardy_tasks"), "weighted_tardiness": f("weighted_tardiness"),
                "total_tardiness": f("total_tardiness"), "utilization": f("utilization"), "conflicts": f("conflicts"),
                "objective": f("objective"), "runtime_ms": f("runtime_ms"),
                "wins_or_ties_best": sum(1 for i in range(n) if r[i]["objective"] <= min(rows[b][i]["objective"] for b in ALGOS))}
    return {"scenarios": n, "jobs_per_scenario": njobs, "machines": nmachines, "algorithms": {a: agg(a) for a in ALGOS}}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--time-limit", type=float, default=6.0)
    a = ap.parse_args()
    main(a.n, a.time_limit)

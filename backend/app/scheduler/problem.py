"""Scheduling problem model, built from the database state.

All times are integer hours RELATIVE to 'now' (the simulation clock).
The problem is a *flexible job shop* with precedence constraints, release times
(component readiness), machine availability and deadlines.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .. import models as m


@dataclass
class Job:
    id: str
    name: str
    duration: int
    priority: int
    deadline: int                 # relative to now (can be negative = already late)
    ws_type: str
    preds: list[str] = field(default_factory=list)      # pending predecessors (to be scheduled)
    release: int = 0                                     # earliest start from components / running predecessors
    release_comp: int = 0
    release_comp_ref: str | None = None                  # binding component id
    release_pred: int = 0                                # end of a running predecessor
    release_pred_ref: str | None = None
    order: int = 0


@dataclass
class Machine:
    id: str
    ws_type: str
    free_at: int = 0
    free_ref: str | None = None      # task currently occupying it (or 'DOWN')


@dataclass
class Problem:
    now: int
    jobs: dict[str, Job]
    machines: dict[str, Machine]
    comp_names: dict[str, str] = field(default_factory=dict)
    job_names: dict[str, str] = field(default_factory=dict)

    def machines_of(self, ws_type: str) -> list[Machine]:
        return [mc for mc in self.machines.values() if mc.ws_type == ws_type]


@dataclass
class Solution:
    assign: dict[str, tuple[str, int, int]]   # job -> (machine, start, end)  (relative hours)
    algorithm: str
    runtime_ms: float = 0.0
    optimal: bool | None = None
    note: str = ""


def build_problem(db) -> Problem:
    now = db.get(m.SimState, 1).now_hour
    tasks = {t.id: t for t in db.query(m.Task).all()}
    deps: dict[str, list[str]] = {}
    for d in db.query(m.TaskDependency).all():
        deps.setdefault(d.task_id, []).append(d.depends_on_id)
    reqs: dict[str, list[m.TaskRequirement]] = {}
    for r in db.query(m.TaskRequirement).all():
        reqs.setdefault(r.task_id, []).append(r)
    comps = {c.id: c for c in db.query(m.Component).all()}

    machines: dict[str, Machine] = {}
    for ws in db.query(m.Workstation).order_by(m.Workstation.id).all():
        free = max(0, ws.available_from - now)
        ref = None
        occ = [t for t in tasks.values() if t.status == m.T_IN_PROGRESS and t.workstation_id == ws.id]
        if occ:
            ref = occ[0].id
        if ws.status == "DOWN":
            ref = "DOWN"
        machines[ws.id] = Machine(ws.id, ws.ws_type, free, ref)

    jobs: dict[str, Job] = {}
    for i, t in enumerate(sorted(tasks.values(), key=lambda x: x.id)):
        if t.status != m.T_PENDING:
            continue
        job = Job(t.id, t.name, t.duration, t.priority, t.deadline_hour - now, t.ws_type, order=i)
        for dep in deps.get(t.id, []):
            dt = tasks[dep]
            if dt.status == m.T_PENDING:
                job.preds.append(dep)
            elif dt.status == m.T_IN_PROGRESS:
                end = max(0, (dt.end_hour or now) - now)
                if end >= job.release_pred:
                    job.release_pred, job.release_pred_ref = end, dep
        for r in reqs.get(t.id, []):
            c = comps[r.component_id]
            if c.status in m.USABLE and c.quantity >= r.quantity:
                ready = 0
            else:
                ready = max(0, c.expected_ready_hour - now)
            if ready > job.release_comp:
                job.release_comp, job.release_comp_ref = ready, c.id
        job.release = max(job.release_comp, job.release_pred)
        jobs[t.id] = job
    return Problem(now=now, jobs=jobs, machines=machines,
                   comp_names={c.id: c.name for c in comps.values()},
                   job_names={t.id: t.name for t in tasks.values()})

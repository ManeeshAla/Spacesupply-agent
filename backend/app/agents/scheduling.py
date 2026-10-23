"""Assembly Scheduling Agent: builds problems from live data, runs solvers, versions schedules, explains decisions."""
from __future__ import annotations

import json

from .. import models as m
from ..config import SOLVER_TIME_LIMIT_S
from ..scheduler import ALGORITHMS, build_problem, evaluate, explain, solve
from .base import fmt, log, now_hour

NAME = "Scheduling Agent"


class SchedulingAgent:
    # ------------------------------------------------------------------ planning
    def plan(self, db, algorithm: str = "CPSAT", trigger: str = "manual") -> dict:
        algorithm = algorithm.upper()
        now = now_hour(db)
        problem = build_problem(db)
        kw = {"time_limit_s": SOLVER_TIME_LIMIT_S} if algorithm == "CPSAT" else {}
        sol = solve(problem, algorithm, **kw)
        metrics = evaluate(problem, sol)
        reasons = explain(problem, sol)

        prev = db.query(m.ScheduleVersion).filter(m.ScheduleVersion.is_current.is_(True)).first()
        prev_entries = {}
        if prev:
            prev_entries = {e.task_id: e for e in db.query(m.ScheduleEntry).filter(m.ScheduleEntry.version_id == prev.id)}
            prev.is_current = False
        ver = m.ScheduleVersion(created_hour=now, algorithm=algorithm, trigger=trigger,
                                metrics_json=json.dumps(metrics), is_current=True)
        db.add(ver)
        db.flush()
        changes = []
        for jid, (mid, s, e) in sol.assign.items():
            r = reasons[jid]
            db.add(m.ScheduleEntry(version_id=ver.id, task_id=jid, workstation_id=mid, start_hour=s + now, end_hour=e + now,
                                   reason_type=r["reason_type"], reason_text=r["reason_text"], binding_ref=r["binding_ref"]))
            old = prev_entries.get(jid)
            if old and (old.start_hour != s + now or old.workstation_id != mid):
                changes.append({"task_id": jid, "name": problem.jobs[jid].name, "old_start": old.start_hour, "new_start": s + now,
                                "delta_hours": s + now - old.start_hour, "old_workstation": old.workstation_id, "new_workstation": mid,
                                "reason_type": r["reason_type"], "reason": r["reason_text"]})
        changes.sort(key=lambda c: -abs(c["delta_hours"]))
        log(db, NAME, f"Re-planned with {algorithm} ({trigger}): makespan {metrics['makespan']}h, "
                      f"{metrics['tardy_tasks']} late task(s), {len(changes)} change(s).")
        db.flush()
        return {"version_id": ver.id, "algorithm": algorithm, "trigger": trigger, "metrics": metrics, "changes": changes,
                "solver_note": sol.note}

    def current_version(self, db) -> m.ScheduleVersion | None:
        return db.query(m.ScheduleVersion).filter(m.ScheduleVersion.is_current.is_(True)).first()

    def first_version_starts(self, db) -> dict[str, int]:
        v = db.query(m.ScheduleVersion).order_by(m.ScheduleVersion.id).first()
        if not v:
            return {}
        return {e.task_id: e.start_hour for e in db.query(m.ScheduleEntry).filter(m.ScheduleEntry.version_id == v.id)}

    def schedule_rows(self, db) -> list[dict]:
        """All tasks with actual (done/running) or planned (pending) timing."""
        ver = self.current_version(db)
        entries = {e.task_id: e for e in db.query(m.ScheduleEntry).filter(m.ScheduleEntry.version_id == ver.id)} if ver else {}
        original = self.first_version_starts(db)
        deps: dict[str, list[str]] = {}
        for d in db.query(m.TaskDependency).all():
            deps.setdefault(d.task_id, []).append(d.depends_on_id)
        rows = []
        for t in db.query(m.Task).order_by(m.Task.id).all():
            e = entries.get(t.id)
            if t.status == m.T_PENDING and e:
                start, end, ws = e.start_hour, e.end_hour, e.workstation_id
            else:
                start, end, ws = t.start_hour, t.end_hour, t.workstation_id
            late = max(0, (end or 0) - t.deadline_hour) if t.status != m.T_COMPLETED else 0
            rows.append({"id": t.id, "name": t.name, "stage_id": t.stage_id, "status": t.status, "workstation": ws,
                         "ws_type": t.ws_type, "start_hour": start, "end_hour": end, "duration": t.duration,
                         "priority": t.priority, "deadline_hour": t.deadline_hour, "late_hours": late,
                         "depends_on": deps.get(t.id, []),
                         "original_start": original.get(t.id) if t.status == m.T_PENDING else None,
                         "shift_hours": (e.start_hour - original[t.id]) if (e and t.id in original and t.status == m.T_PENDING) else 0,
                         "binding_ref": e.binding_ref if (e and t.status == m.T_PENDING) else None,
                         "reason_type": e.reason_type if (e and t.status == m.T_PENDING) else None,
                         "reason_text": e.reason_text if (e and t.status == m.T_PENDING) else None})
        return rows

    # ------------------------------------------------------------------ readiness
    def task_readiness(self, db, task_id: str) -> dict:
        t = db.get(m.Task, task_id)
        now = now_hour(db)
        blockers = []
        if t.status == m.T_COMPLETED:
            return {"task_id": t.id, "name": t.name, "status": t.status, "can_start_now": False, "blockers": [],
                    "summary": "already completed", "components": []}
        if t.status == m.T_IN_PROGRESS:
            return {"task_id": t.id, "name": t.name, "status": t.status, "can_start_now": False, "blockers": [],
                    "summary": f"already in progress on {t.workstation_id} (ends in {max(0, t.end_hour - now)}h)", "components": []}
        for d in db.query(m.TaskDependency).filter(m.TaskDependency.task_id == t.id):
            p = db.get(m.Task, d.depends_on_id)
            if p.status != m.T_COMPLETED:
                eta = (p.end_hour - now) if p.status == m.T_IN_PROGRESS else None
                blockers.append({"type": "PREDECESSOR", "ref": p.id, "text": f"Predecessor {p.id} '{p.name}' is {p.status.lower().replace('_', ' ')}",
                                 "eta_hours": eta})
        comps = []
        for rq in db.query(m.TaskRequirement).filter(m.TaskRequirement.task_id == t.id):
            c = db.get(m.Component, rq.component_id)
            ok = c.status in m.USABLE and c.quantity >= rq.quantity
            eta = 0 if ok else max(0, c.expected_ready_hour - now)
            comps.append({"id": c.id, "name": c.name, "status": c.status, "needed": rq.quantity, "on_hand": c.quantity,
                          "ready": ok, "eta_hours": eta, "criticality": c.criticality,
                          "delayed": c.delay_hours > 0})
            if not ok:
                why = {m.ORDERED: "still on order", m.RECEIVED: "received, not inspected", m.INSPECTION_PENDING: "awaiting inspection",
                       m.IN_INSPECTION: "in inspection", m.REJECTED: "rejected (replacement pending)"}.get(c.status, "short on quantity")
                extra = f", delivery delayed {c.delay_hours}h" if c.delay_hours else ""
                blockers.append({"type": "COMPONENT", "ref": c.id, "text": f"{c.id} {c.name} {why}{extra}; usable in ~{eta}h", "eta_hours": eta})
        free = [w for w in db.query(m.Workstation).filter(m.Workstation.ws_type == t.ws_type).all()
                if w.status == "AVAILABLE" and w.available_from <= now]
        if not free:
            soon = min((w.available_from for w in db.query(m.Workstation).filter(m.Workstation.ws_type == t.ws_type)), default=now)
            blockers.append({"type": "WORKSTATION", "ref": t.ws_type, "text": f"No {t.ws_type.lower()} workstation free; next free in {max(0, soon - now)}h",
                             "eta_hours": max(0, soon - now)})
        ver = self.current_version(db)
        e = (db.query(m.ScheduleEntry).filter(m.ScheduleEntry.version_id == ver.id, m.ScheduleEntry.task_id == t.id).first()) if ver else None
        return {"task_id": t.id, "name": t.name, "status": t.status, "stage_id": t.stage_id,
                "can_start_now": not blockers, "blockers": blockers, "components": comps,
                "planned_start_hour": e.start_hour if e else None, "planned_workstation": e.workstation_id if e else None,
                "planned_in_hours": (e.start_hour - now) if e else None,
                "summary": "ready to start now" if not blockers else f"blocked by {len(blockers)} issue(s)"}

    def stage_readiness(self, db, stage_id: int) -> dict:
        tasks = db.query(m.Task).filter(m.Task.stage_id == stage_id).order_by(m.Task.id).all()
        pending = [t for t in tasks if t.status == m.T_PENDING]
        st = db.get(m.Stage, stage_id)
        if not pending:
            return {"stage_id": stage_id, "stage": st.name, "ready": True, "complete": all(t.status == m.T_COMPLETED for t in tasks),
                    "frontier": [], "blockers": [], "summary": "no pending tasks"}
        frontier = []
        for t in pending:
            if all(db.get(m.Task, d.depends_on_id).status == m.T_COMPLETED
                   for d in db.query(m.TaskDependency).filter(m.TaskDependency.task_id == t.id)):
                frontier.append(self.task_readiness(db, t.id))
        # a stage is "ready to continue" when every currently-eligible task could start now
        ready = bool(frontier) and all(f["can_start_now"] for f in frontier)
        if not frontier:
            ready = False
        blockers = []
        for f in frontier:
            for b in f["blockers"]:
                blockers.append({**b, "task_id": f["task_id"], "task": f["name"]})
        return {"stage_id": stage_id, "stage": st.name, "ready": ready, "complete": False, "frontier": frontier, "blockers": blockers,
                "summary": "ready" if ready else f"{len(blockers)} blocking issue(s) on {len(frontier)} eligible task(s)"}

    # ------------------------------------------------------------------ explanation
    def explain_task(self, db, task_id: str) -> dict:
        t = db.get(m.Task, task_id)
        ver = self.current_version(db)
        entries = {e.task_id: e for e in db.query(m.ScheduleEntry).filter(m.ScheduleEntry.version_id == ver.id)} if ver else {}
        e = entries.get(task_id)
        original = self.first_version_starts(db).get(task_id)
        now = now_hour(db)
        out = {"task_id": task_id, "name": t.name, "status": t.status, "deadline_hour": t.deadline_hour}
        if t.status != m.T_PENDING or not e:
            out.update({"planned_start_hour": t.start_hour, "planned_end_hour": t.end_hour, "chain": [], "shift_hours": 0,
                        "original_start_hour": t.start_hour})
            return out
        chain: list[str] = []
        cur = e
        for _ in range(7):
            chain.append(f"{cur.task_id}: {cur.reason_text}")
            if cur.reason_type == "COMPONENT" and cur.binding_ref:
                c = db.get(m.Component, cur.binding_ref)
                d = self.open_delivery(db, c.id)
                if d is not None:
                    chain.append(f"{c.id} {c.name}: supplier {c.supplier.name}, delivery {d.id} {d.status.lower().replace('_', ' ')}"
                                 + (f" by {d.delay_hours}h" if d.delay_hours else "") + f", ETA +{max(0, d.eta_hour - now)}h")
                break
            nxt = entries.get(cur.binding_ref) if cur.reason_type in ("PREDECESSOR", "WORKSTATION") and cur.binding_ref else None
            if nxt is None:
                break
            cur = nxt
        out.update({"planned_start_hour": e.start_hour, "planned_end_hour": e.end_hour, "workstation": e.workstation_id,
                    "original_start_hour": original, "shift_hours": (e.start_hour - original) if original is not None else 0,
                    "late_hours": max(0, e.end_hour - t.deadline_hour), "reason_type": e.reason_type, "reason": e.reason_text,
                    "chain": chain})
        return out

    @staticmethod
    def open_delivery(db, cid: str):
        return (db.query(m.Delivery).filter(m.Delivery.component_id == cid, m.Delivery.status.in_(["ON_TIME", "DELAYED", "ARRIVED"]))
                .order_by(m.Delivery.eta_hour).first())

    def delayed_tasks(self, db) -> list[dict]:
        rows = self.schedule_rows(db)
        return sorted([r for r in rows if r["status"] == m.T_PENDING and (r["late_hours"] > 0 or r["shift_hours"] > 0)],
                      key=lambda r: (-r["late_hours"], -r["shift_hours"]))

    # ------------------------------------------------------------------ comparison
    def compare(self, db, time_limit_s: float = 4.0) -> list[dict]:
        problem = build_problem(db)
        out = []
        for name in ALGORITHMS:
            kw = {"time_limit_s": time_limit_s} if name == "CPSAT" else {}
            met = evaluate(problem, solve(problem, name, **kw))
            out.append({"algorithm": name, **met})
        return out

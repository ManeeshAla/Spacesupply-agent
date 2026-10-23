"""Simulation + autonomy engine.

`Engine.handle_event` is the autonomous loop:
   event -> (Supply/Tracking agent applies it) -> Scheduling agent re-plans with OR-Tools
         -> Monitoring agent scans + raises alerts -> dashboard/chat can explain the change.
"""
from __future__ import annotations

import json

from . import models as m
from . import seed as seed_mod
from .agents.base import fmt, iso, log, now_hour
from .agents.monitoring import MonitoringAgent
from .agents.scheduling import SchedulingAgent
from .agents.supply import SupplyAgent
from .agents.tracking import TrackingAgent
from .config import MICROLM_METRICS
from .lifecycle import INSPECTION_HOURS

AGENTS = ["Tracking Agent", "Supply Agent", "Scheduling Agent", "Monitoring Agent", "Language Agent"]


class Engine:
    def __init__(self):
        self.tracking = TrackingAgent()
        self.supply = SupplyAgent()
        self.scheduling = SchedulingAgent()
        self.monitoring = MonitoringAgent()

    # ------------------------------------------------------------------ lifecycle
    def bootstrap(self, db) -> None:
        seed_mod.ensure_seeded(db)
        if self.scheduling.current_version(db) is None:
            self.scheduling.plan(db, "CPSAT", trigger="Initial plan")
            self.monitoring.scan(db)
            log(db, "Language Agent", "Micro LM online: intent + entity extraction ready.")
            db.commit()

    def reset(self, db) -> None:
        db.close()
        seed_mod.reset_schema()
        self.bootstrap(db)

    # ------------------------------------------------------------------ events
    def handle_event(self, db, event: dict) -> dict:
        kind = (event.get("type") or "").upper()
        steps: list[dict] = []
        before = self._kpis(db)
        if kind == "SUPPLIER_DELAY":
            cid, hours = event["component_id"], int(event.get("hours", 24))
            impact = self.supply.register_delay(db, cid, hours)
            steps.append({"agent": "Supply Agent", "action": f"Registered {hours}h delay on {cid} ({impact['name']}) from {impact['supplier']}; "
                                                              f"directly blocks {impact['directly_affected'] or 'no pending task'}, "
                                                              f"{len(impact['downstream_affected'])} downstream task(s) at risk."})
            trigger = f"Supplier delay: {cid} +{hours}h"
        elif kind == "REJECT_COMPONENT":
            cid = event["component_id"]
            res = self.tracking.reject(db, cid, int(event.get("replacement_hours", 36)))
            steps.append({"agent": "Tracking Agent", "action": f"{cid} rejected; replacement {res['replacement_delivery']} ordered (ETA +{res['eta_hour'] - now_hour(db)}h)."})
            impact = res
            trigger = f"Component rejected: {cid}"
        elif kind == "WORKSTATION_DOWN":
            wid, hours = event["workstation_id"], int(event.get("hours", 24))
            ws = db.get(m.Workstation, wid)
            if ws is None:
                raise ValueError(f"Unknown workstation {wid}")
            ws.status = "DOWN"
            ws.available_from = max(ws.available_from, now_hour(db)) + hours
            log(db, "Monitoring Agent", f"{wid} reported down for {hours}h.")
            steps.append({"agent": "Monitoring Agent", "action": f"{wid} ({ws.name}) is down for {hours}h."})
            impact = {"workstation": wid, "hours": hours}
            trigger = f"Workstation down: {wid} {hours}h"
        elif kind == "ADVANCE_TIME":
            return self.advance(db, int(event.get("hours", 24)))
        else:
            raise ValueError(f"Unknown event type '{kind}'")

        res = self.scheduling.plan(db, "CPSAT", trigger=trigger)
        steps.append({"agent": "Scheduling Agent",
                      "action": f"Re-planned with OR-Tools CP-SAT: {len(res['changes'])} task(s) moved, {res['metrics']['tardy_tasks']} projected late, "
                                f"makespan {res['metrics']['makespan']}h."})
        mon = self.monitoring.scan(db)
        steps.append({"agent": "Monitoring Agent", "action": f"Scan complete: {len(mon['created'])} new alert(s), {mon['resolved']} resolved."})
        if res["changes"]:
            top = res["changes"][:3]
            body = "; ".join(f"{c['task_id']} {c['name']}: {self._sign(c['delta_hours'])}h" for c in top)
            alert = self.monitoring.post_info(db, f"SCHEDULE_CHANGE:{res['version_id']}", f"Schedule changed – {trigger}",
                                              f"{len(res['changes'])} task(s) rescheduled. Largest: {body}. Cause: {top[0]['reason']}",
                                              top[0]["task_id"])
        db.commit()
        after = self._kpis(db)
        return {"event": event, "trigger": trigger, "impact": impact, "steps": steps, "schedule_changes": res["changes"][:15],
                "before": before, "after": after, "version_id": res["version_id"]}

    @staticmethod
    def _sign(h: int) -> str:
        return f"+{h}" if h >= 0 else str(h)

    def _kpis(self, db) -> dict:
        v = self.scheduling.current_version(db)
        met = json.loads(v.metrics_json) if v else {}
        rows = self.scheduling.schedule_rows(db)
        final = next((r for r in rows if r["id"] == "T-039"), None)
        return {"makespan": met.get("makespan"), "tardy_tasks": met.get("tardy_tasks"), "weighted_tardiness": met.get("weighted_tardiness"),
                "launch_readiness_hour": final["end_hour"] if final else None,
                "launch_readiness": fmt(db, final["end_hour"]) if final and final["end_hour"] is not None else None,
                "launch_readiness_late_hours": final["late_hours"] if final else None}

    # ------------------------------------------------------------------ time
    def advance(self, db, hours: int) -> dict:
        hours = max(1, min(int(hours), 240))
        start = now_hour(db)
        log_lines: list[str] = []
        replans = 0
        for _ in range(hours):
            t = now_hour(db) + 1
            db.get(m.SimState, 1).now_hour = t
            drift = self._tick(db, t, log_lines)
            db.flush()
            if drift:
                self.scheduling.plan(db, "CPSAT", trigger="Plan drift (task could not start as planned)")
                replans += 1
        mon = self.monitoring.scan(db)
        log(db, "Scheduling Agent" if replans else "Tracking Agent", f"Advanced simulation {hours}h to {fmt(db, now_hour(db))}; {len(log_lines)} state change(s).")
        db.commit()
        return {"event": {"type": "ADVANCE_TIME", "hours": hours}, "from_hour": start, "to_hour": now_hour(db), "now": iso(db, now_hour(db)),
                "changes": log_lines[-40:], "replans": replans, "alerts": mon, "steps": [
                    {"agent": "Tracking Agent", "action": f"Advanced {hours}h; {len(log_lines)} lifecycle/task changes."},
                    {"agent": "Monitoring Agent", "action": f"Scan complete: {len(mon['created'])} new alert(s), {mon['resolved']} resolved."}],
                "after": self._kpis(db)}

    def _tick(self, db, t: int, out: list[str]) -> bool:
        tr = self.tracking
        drift = False
        # 1. deliveries arriving
        for d in db.query(m.Delivery).filter(m.Delivery.status.in_(["ON_TIME", "DELAYED"]), m.Delivery.eta_hour <= t).all():
            c = d.component
            d.status = "ARRIVED"
            if c.status in (m.ORDERED, m.REJECTED):
                tr.transition(db, c, m.RECEIVED, note=f"Delivery {d.id} arrived", hour=t)
                tr.transition(db, c, m.INSPECTION_PENDING, hour=t)
            else:
                db.add(m.ComponentEvent(component_id=c.id, hour=t, event_type="TOPUP_RECEIVED", from_status=c.status, to_status=c.status,
                                        location=c.location, note=f"Top-up delivery {d.id} ({d.quantity} units) arrived; inspecting"))
            out.append(f"{c.id} {c.name}: delivery {d.id} arrived")
        # 2. inspection progress & clearance
        for c in db.query(m.Component).filter(m.Component.status.in_([m.RECEIVED, m.INSPECTION_PENDING, m.IN_INSPECTION])).all():
            if c.status == m.RECEIVED:
                tr.transition(db, c, m.INSPECTION_PENDING, hour=t)
            if c.status == m.INSPECTION_PENDING and t >= c.expected_ready_hour - 5:
                tr.transition(db, c, m.IN_INSPECTION, hour=t)
                out.append(f"{c.id} {c.name}: inspection started")
            if c.status == m.IN_INSPECTION and t >= c.expected_ready_hour:
                tr.transition(db, c, m.APPROVED, hour=t, note="Inspection passed")
                tr.transition(db, c, m.IN_WAREHOUSE, hour=t)
                self._apply_arrived(db, c)
                out.append(f"{c.id} {c.name}: approved -> warehouse")
        for c in db.query(m.Component).filter(m.Component.status.in_([m.APPROVED, m.IN_WAREHOUSE])).all():
            if t >= c.expected_ready_hour and self._apply_arrived(db, c):
                out.append(f"{c.id} {c.name}: top-up cleared (+units on hand)")
        # 3. workstation repairs
        for w in db.query(m.Workstation).filter(m.Workstation.status == "DOWN", m.Workstation.available_from <= t).all():
            w.status = "AVAILABLE"
            log(db, "Monitoring Agent", f"{w.id} back in service.")
            out.append(f"{w.id} back in service")
        # 4. task completions
        for task in db.query(m.Task).filter(m.Task.status == m.T_IN_PROGRESS, m.Task.end_hour <= t).all():
            task.status = m.T_COMPLETED
            for rq in db.query(m.TaskRequirement).filter(m.TaskRequirement.task_id == task.id):
                c = db.get(m.Component, rq.component_id)
                if c.status == m.IN_ASSEMBLY_BAY:
                    tr.transition(db, c, m.INSTALLED, hour=t, note=f"Installed during {task.id} {task.name}")
                    c.required_quantity = 0
            out.append(f"{task.id} {task.name}: COMPLETED")
        # 5. task starts according to the current plan
        ver = self.scheduling.current_version(db)
        if ver:
            entries = (db.query(m.ScheduleEntry).filter(m.ScheduleEntry.version_id == ver.id).order_by(m.ScheduleEntry.start_hour).all())
            for e in entries:
                task = db.get(m.Task, e.task_id)
                if task.status != m.T_PENDING or e.start_hour > t:
                    continue
                ok = all(db.get(m.Task, d.depends_on_id).status == m.T_COMPLETED
                         for d in db.query(m.TaskDependency).filter(m.TaskDependency.task_id == task.id))
                reqs = db.query(m.TaskRequirement).filter(m.TaskRequirement.task_id == task.id).all()
                comps_ok = all(db.get(m.Component, r.component_id).status in m.USABLE and db.get(m.Component, r.component_id).quantity >= r.quantity
                               for r in reqs)
                ws = db.get(m.Workstation, e.workstation_id)
                busy = db.query(m.Task).filter(m.Task.status == m.T_IN_PROGRESS, m.Task.workstation_id == ws.id).count() > 0
                if ok and comps_ok and ws.status == "AVAILABLE" and ws.available_from <= t and not busy:
                    task.status, task.workstation_id, task.start_hour, task.end_hour = m.T_IN_PROGRESS, ws.id, t, t + task.duration
                    ws.available_from = t + task.duration
                    for r in reqs:
                        c = db.get(m.Component, r.component_id)
                        if c.status == m.APPROVED:
                            tr.transition(db, c, m.IN_WAREHOUSE, hour=t)
                        if c.status == m.IN_WAREHOUSE:
                            tr.transition(db, c, m.IN_ASSEMBLY_BAY, hour=t, location=f"Assembly Bay – {ws.id}")
                    out.append(f"{task.id} {task.name}: STARTED on {ws.id}")
                else:
                    drift = True
        return drift

    @staticmethod
    def _apply_arrived(db, c: m.Component) -> bool:
        applied = False
        for d in db.query(m.Delivery).filter(m.Delivery.component_id == c.id, m.Delivery.status == "ARRIVED").all():
            c.quantity += d.quantity
            d.status = "CLEARED"
            applied = True
        return applied

    # ------------------------------------------------------------------ supervisor
    def supervisor_cycle(self, db) -> dict:
        res = self.monitoring.scan(db)
        db.commit()
        return res

    # ------------------------------------------------------------------ dashboard
    def system_status(self, db) -> str:
        crit = db.query(m.Alert).filter(m.Alert.status == "OPEN", m.Alert.severity == "CRITICAL").count()
        warn = db.query(m.Alert).filter(m.Alert.status == "OPEN", m.Alert.severity == "WARNING").count()
        return "DEGRADED" if crit else ("ATTENTION" if warn else "OPERATIONAL")

    def agent_status(self, db) -> list[dict]:
        out = []
        for name in AGENTS:
            last = db.query(m.AgentLog).filter(m.AgentLog.agent == name).order_by(m.AgentLog.id.desc()).first()
            n = db.query(m.AgentLog).filter(m.AgentLog.agent == name).count()
            out.append({"name": name, "status": "ACTIVE", "last_action": last.message if last else "Idle",
                        "last_hour": last.hour if last else None, "actions": n})
        return out

    def progress_series(self, db) -> dict:
        rows = self.scheduling.schedule_rows(db)
        now = now_hour(db)
        end = max([r["end_hour"] for r in rows if r["end_hour"] is not None] + [now + 24])
        points = list(range(min(now - 96, -96), end + 24, 12))
        tasks_by_stage: dict[int, list[dict]] = {}
        for r in rows:
            tasks_by_stage.setdefault(r["stage_id"], []).append(r)
        series = []
        for h in points:
            row = {"hour": h, "label": fmt(db, h), "projected": h > now}
            for sid, ts in tasks_by_stage.items():
                total = sum(t["duration"] for t in ts)
                done = 0.0
                for t in ts:
                    s, e = t["start_hour"], t["end_hour"]
                    if s is None or e is None:
                        continue
                    done += t["duration"] * min(1.0, max(0.0, (h - s) / max(1, e - s)))
                row[f"s{sid}"] = round(100 * done / total, 1)
            series.append(row)
        return {"now": now, "points": series}

    def dashboard(self, db) -> dict:
        now = now_hour(db)
        rows = self.scheduling.schedule_rows(db)
        stages = self.tracking.stage_progress(db)
        groups = self.tracking.component_groups(db)
        inv = self.supply.summary(db)
        open_alerts = db.query(m.Alert).filter(m.Alert.status == "OPEN").order_by(m.Alert.id.desc()).all()
        sev_rank = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
        top_alerts = sorted(open_alerts, key=lambda a: (sev_rank[a.severity], -a.id))[:5]
        today = [r for r in rows if r["status"] == m.T_IN_PROGRESS or
                 (r["status"] == m.T_PENDING and r["start_hour"] is not None and r["start_hour"] - now <= 24)]
        today.sort(key=lambda r: (r["start_hour"] if r["start_hour"] is not None else 0))
        deliveries = (db.query(m.Delivery).filter(m.Delivery.status.in_(["ON_TIME", "DELAYED"])).order_by(m.Delivery.eta_hour).limit(8).all())
        units = sum(c.quantity for c in db.query(m.Component).all()) + sum(d.quantity for d in db.query(m.Delivery).filter(m.Delivery.status != "CLEARED"))
        metrics = json.loads(MICROLM_METRICS.read_text()) if MICROLM_METRICS.exists() else {}
        return {
            "now_iso": iso(db, now), "now_hour": now, "system_status": self.system_status(db),
            "agents": self.agent_status(db),
            "kpis": {"component_lots": db.query(m.Component).count(), "component_units": units,
                     "ongoing_tasks": sum(1 for r in rows if r["status"] == m.T_IN_PROGRESS),
                     "planned_next_24h": sum(1 for r in rows if r["status"] == m.T_PENDING and r["start_hour"] is not None and r["start_hour"] - now <= 24),
                     "pending_alerts": len(open_alerts), "active_agents": len(AGENTS), "total_agents": len(AGENTS)},
            "stages": stages, "component_status": groups, "inventory": inv,
            "todays_schedule": [{"id": r["id"], "name": r["name"], "workstation": r["workstation"], "time": fmt(db, r["start_hour"]) if r["start_hour"] is not None else "-",
                                 "status": "In Progress" if r["status"] == m.T_IN_PROGRESS else "Scheduled"} for r in today[:8]],
            "alerts": [self.alert_dict(db, a) for a in top_alerts],
            "deliveries": [{"id": d.id, "component_id": d.component_id, "component": d.component.name, "eta": fmt(db, d.eta_hour),
                            "eta_hours": d.eta_hour - now, "supplier": d.supplier.name, "status": d.status,
                            "delay_hours": d.delay_hours, "replacement": d.is_replacement} for d in deliveries],
            "progress": self.progress_series(db),
            "launch": self._kpis(db),
            "microlm": {"parameters": metrics.get("parameters"), "intent_accuracy": (metrics.get("test") or {}).get("intent_accuracy"),
                        "entity_f1": (metrics.get("test") or {}).get("entity_f1")},
        }

    def alert_dict(self, db, a: m.Alert) -> dict:
        return {"id": a.id, "severity": a.severity, "category": a.category, "title": a.title, "message": a.message,
                "task_id": a.task_id, "component_id": a.component_id, "status": a.status, "time": fmt(db, a.created_hour),
                "created_hour": a.created_hour}


engine = Engine()

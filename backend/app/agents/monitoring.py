"""Monitoring Agent: continuously scans the system, raises / resolves alerts."""
from __future__ import annotations

from .. import models as m
from .base import fmt, log, now_hour
from .scheduling import SchedulingAgent

NAME = "Monitoring Agent"
MANAGED = ("DELIVERY_DELAY", "COMPONENT_REJECTED", "INSPECTION_PENDING", "WORKSTATION_DOWN", "MAINTENANCE_DUE", "TASK_LATE")


class MonitoringAgent:
    def __init__(self):
        self.scheduler = SchedulingAgent()

    def _upsert(self, db, active: set, key, severity, category, title, message, task_id=None, component_id=None):
        active.add(key)
        existing = (db.query(m.Alert).filter(m.Alert.dedupe_key == key, m.Alert.status != "RESOLVED").first())
        if existing:
            if existing.message != message or existing.severity != severity or existing.title != title:
                existing.message, existing.severity, existing.title = message, severity, title
            return None
        a = m.Alert(dedupe_key=key, severity=severity, category=category, title=title, message=message,
                    task_id=task_id, component_id=component_id, created_hour=now_hour(db))
        db.add(a)
        return a

    def post_info(self, db, key: str, title: str, message: str, task_id=None, component_id=None) -> m.Alert:
        a = m.Alert(dedupe_key=key, severity="INFO", category="SCHEDULE_CHANGE", title=title, message=message,
                    task_id=task_id, component_id=component_id, created_hour=now_hour(db))
        db.add(a)
        return a

    def scan(self, db) -> dict:
        now = now_hour(db)
        active: set[str] = set()
        created: list[m.Alert] = []
        comps = {c.id: c for c in db.query(m.Component).all()}
        reqs: dict[str, list[str]] = {}
        for r in db.query(m.TaskRequirement).all():
            reqs.setdefault(r.component_id, []).append(r.task_id)
        tasks = {t.id: t for t in db.query(m.Task).all()}
        rows = {r["id"]: r for r in self.scheduler.schedule_rows(db)}

        def pending_users(cid):
            return [tasks[t] for t in reqs.get(cid, []) if tasks[t].status == m.T_PENDING]

        # 1. delayed deliveries
        for d in db.query(m.Delivery).filter(m.Delivery.status == "DELAYED").all():
            c = comps[d.component_id]
            users = pending_users(c.id)
            if not users:
                continue
            late = [u for u in users if rows[u.id]["late_hours"] > 0]
            binding = [u for u in users if rows[u.id]["reason_type"] == "COMPONENT" and rows[u.id]["binding_ref"] == c.id]
            sev = "CRITICAL" if (late or binding) else "WARNING"
            msg = (f"{d.id} from {c.supplier.name} delayed by {d.delay_hours}h; new ETA {fmt(db, d.eta_hour)}. "
                   f"Needed by {', '.join(u.id + ' ' + u.name for u in users)}.")
            a = self._upsert(db, active, f"DELIVERY_DELAY:{c.id}", sev, "DELIVERY_DELAY",
                             f"{c.id} ({c.name}) delivery delayed", msg, users[0].id, c.id)
            if a: created.append(a)
        # 2. rejected components
        for c in comps.values():
            if c.status == m.REJECTED and pending_users(c.id):
                d = self.scheduler.open_delivery(db, c.id)
                eta = f" Replacement ETA {fmt(db, d.eta_hour)}." if d else " No replacement ordered!"
                users = pending_users(c.id)
                blocking = any(rows[u.id]["reason_type"] == "COMPONENT" and rows[u.id]["binding_ref"] == c.id or rows[u.id]["late_hours"] > 0
                               for u in users)
                a = self._upsert(db, active, f"COMPONENT_REJECTED:{c.id}", "CRITICAL" if blocking else "WARNING",
                                 "COMPONENT_REJECTED", f"{c.id} ({c.name}) rejected in inspection",
                                 f"Failed inspection and is in quarantine.{eta}", pending_users(c.id)[0].id, c.id)
                if a: created.append(a)
        # 3. inspection backlog blocking near-term tasks
        starts = {tid: r["start_hour"] for tid, r in rows.items() if r["status"] == m.T_PENDING and r["start_hour"] is not None}
        insp = [c for c in comps.values() if c.status in (m.RECEIVED, m.INSPECTION_PENDING, m.IN_INSPECTION)
                and any(starts.get(t.id, 10 ** 6) - now <= 36 for t in pending_users(c.id))]
        if insp:
            a = self._upsert(db, active, "INSPECTION_PENDING", "WARNING", "INSPECTION_PENDING",
                             f"{len(insp)} component(s) inspection pending",
                             "Needed within 36h: " + ", ".join(f"{c.id} {c.name}" for c in insp[:6]) + ("…" if len(insp) > 6 else ""),
                             None, insp[0].id)
            if a: created.append(a)
        # 4. workstations
        for w in db.query(m.Workstation).all():
            if w.status == "DOWN":
                a = self._upsert(db, active, f"WORKSTATION_DOWN:{w.id}", "CRITICAL", "WORKSTATION_DOWN",
                                 f"Workstation {w.id} ({w.name}) is down", f"Back in service {fmt(db, w.available_from)} (in {max(0, w.available_from - now)}h).")
                if a: created.append(a)
            elif w.maintenance_due_hour is not None and 0 <= w.maintenance_due_hour - now <= 72:
                days = (w.maintenance_due_hour - now) / 24
                a = self._upsert(db, active, f"MAINTENANCE_DUE:{w.id}", "WARNING", "MAINTENANCE_DUE",
                                 f"Workstation {w.id} maintenance due in {days:.0f} day(s)" if days >= 1 else f"Workstation {w.id} maintenance due today",
                                 f"{w.name}: scheduled maintenance at {fmt(db, w.maintenance_due_hour)}.")
                if a: created.append(a)
        # 5. projected lateness
        late = sorted([r for r in rows.values() if r["status"] == m.T_PENDING and r["late_hours"] > 0], key=lambda r: -r["late_hours"])
        for r in late[:6]:
            sev = "CRITICAL" if (r["late_hours"] > 24 or r["priority"] >= 5) else "WARNING"
            a = self._upsert(db, active, f"TASK_LATE:{r['id']}", sev, "TASK_LATE",
                             f"{r['id']} '{r['name']}' projected {r['late_hours']}h late",
                             f"Planned finish {fmt(db, r['end_hour'])} vs deadline {fmt(db, r['deadline_hour'])}. {r['reason_text'] or ''}", r["id"])
            if a: created.append(a)
        # resolve conditions that cleared
        resolved = 0
        for a in db.query(m.Alert).filter(m.Alert.status != "RESOLVED", m.Alert.category.in_(MANAGED)).all():
            if a.dedupe_key not in active:
                a.status = "RESOLVED"
                resolved += 1
        db.flush()
        if created or resolved:
            log(db, NAME, f"Scan: {len(created)} new alert(s), {resolved} resolved.")
        return {"created": [a.dedupe_key for a in created], "resolved": resolved,
                "open": db.query(m.Alert).filter(m.Alert.status == "OPEN").count()}

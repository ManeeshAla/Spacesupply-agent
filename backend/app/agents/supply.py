"""Supply / Inventory Agent: stock, shortages, deliveries, supplier delays."""
from __future__ import annotations

from .. import models as m
from .base import log, now_hour

NAME = "Supply Agent"
OPEN_DELIVERY = ["ON_TIME", "DELAYED"]


class SupplyAgent:
    def open_deliveries(self, db, cid: str | None = None):
        q = db.query(m.Delivery).filter(m.Delivery.status.in_(OPEN_DELIVERY))
        if cid:
            q = q.filter(m.Delivery.component_id == cid)
        return q.order_by(m.Delivery.eta_hour).all()

    def inventory_rows(self, db) -> list[dict]:
        rows = []
        deliveries: dict[str, list[m.Delivery]] = {}
        for d in db.query(m.Delivery).filter(m.Delivery.status != "CLEARED").all():
            deliveries.setdefault(d.component_id, []).append(d)
        for c in db.query(m.Component).order_by(m.Component.id).all():
            ds = deliveries.get(c.id, [])
            incoming = sum(d.quantity for d in ds)
            delayed = any(d.status == "DELAYED" for d in ds)
            available = c.quantity if c.status in (m.APPROVED, m.IN_WAREHOUSE) else 0
            pipeline = c.quantity if c.status in (m.RECEIVED, m.INSPECTION_PENDING, m.IN_INSPECTION) else 0
            required = c.required_quantity if c.status not in (m.INSTALLED,) else 0
            if c.status == m.IN_ASSEMBLY_BAY:
                required = 0
            shortage = max(0, required - available)
            if required == 0:
                cls = "DONE"
            elif shortage == 0:
                cls = "SUFFICIENT"
            elif delayed or c.status == m.REJECTED or c.criticality == "CRITICAL":
                cls = "CRITICAL"
            elif incoming >= shortage - pipeline and incoming > 0:
                cls = "ON_ORDER"
            else:
                cls = "LOW"
            eta = min((d.eta_hour for d in ds), default=None)
            eta_in = None if eta is None else eta - now_hour(db)
            rows.append({"id": c.id, "name": c.name, "category": c.category, "stage_id": c.stage_id, "status": c.status,
                         "criticality": c.criticality, "available": available, "pipeline": pipeline, "required": required,
                         "shortage": shortage, "incoming": incoming, "next_eta_hour": eta, "next_eta_in": eta_in, "delayed": delayed,
                         "supplier": c.supplier.name, "class": cls})
        return rows

    def summary(self, db) -> dict:
        s = {"sufficient": 0, "low": 0, "critical": 0, "on_order": 0}
        for r in self.inventory_rows(db):
            k = {"SUFFICIENT": "sufficient", "LOW": "low", "CRITICAL": "critical", "ON_ORDER": "on_order"}.get(r["class"])
            if k:
                s[k] += 1
        return s

    def shortages(self, db, stage_id: int | None = None, task_id: str | None = None) -> list[dict]:
        rows = [r for r in self.inventory_rows(db) if r["shortage"] > 0]
        if stage_id:
            rows = [r for r in rows if r["stage_id"] == stage_id]
        if task_id:
            need = {x.component_id for x in db.query(m.TaskRequirement).filter(m.TaskRequirement.task_id == task_id)}
            rows = [r for r in rows if r["id"] in need]
        tasks_by_comp: dict[str, list[str]] = {}
        for rq in db.query(m.TaskRequirement).all():
            t = db.get(m.Task, rq.task_id)
            if t.status != m.T_COMPLETED:
                tasks_by_comp.setdefault(rq.component_id, []).append(f"{t.id} {t.name}")
        for r in rows:
            r["affected_tasks"] = tasks_by_comp.get(r["id"], [])
        return sorted(rows, key=lambda r: (r["class"] != "CRITICAL", -r["shortage"]))

    def tasks_needing(self, db, cid: str, pending_only: bool = True) -> list[m.Task]:
        out = []
        for rq in db.query(m.TaskRequirement).filter(m.TaskRequirement.component_id == cid):
            t = db.get(m.Task, rq.task_id)
            if not pending_only or t.status == m.T_PENDING:
                out.append(t)
        return out

    def downstream(self, db, task_ids: list[str]) -> list[str]:
        """All pending tasks that (transitively) depend on the given tasks."""
        children: dict[str, list[str]] = {}
        for d in db.query(m.TaskDependency).all():
            children.setdefault(d.depends_on_id, []).append(d.task_id)
        seen, stack = set(), list(task_ids)
        while stack:
            cur = stack.pop()
            for ch in children.get(cur, []):
                if ch not in seen:
                    seen.add(ch)
                    stack.append(ch)
        return sorted(seen)

    # ---------------------------------------------------------------- commands
    def register_delay(self, db, cid: str, hours: int, reason: str = "Supplier delay") -> dict:
        comp = db.get(m.Component, cid)
        if comp is None:
            raise ValueError(f"Unknown component {cid}")
        if hours < 1:
            raise ValueError("Delay must be at least 1 hour")
        deliveries = self.open_deliveries(db, cid)
        if not deliveries:
            raise ValueError(f"{cid} has no open delivery to delay")
        d = deliveries[0]
        d.eta_hour += hours
        d.delay_hours += hours
        d.status = "DELAYED"
        comp.expected_ready_hour += hours
        comp.delay_hours += hours
        db.add(m.ComponentEvent(component_id=cid, hour=now_hour(db), event_type="DELIVERY_DELAYED", from_status=comp.status,
                                to_status=comp.status, location=comp.location,
                                note=f"{reason}: {d.id} delayed {hours}h by {comp.supplier.name}; new ETA +{d.eta_hour - now_hour(db)}h"))
        direct = self.tasks_needing(db, cid)
        downstream = self.downstream(db, [t.id for t in direct])
        log(db, NAME, f"Supplier delay on {cid} ({comp.name}): +{hours}h. Directly blocks {[t.id for t in direct]}; downstream {downstream}.")
        return {"component": cid, "name": comp.name, "delivery": d.id, "supplier": comp.supplier.name, "hours": hours,
                "new_eta_hour": d.eta_hour, "directly_affected": [t.id for t in direct], "downstream_affected": downstream}

    def order_replacement(self, db, comp: m.Component, quantity: int, lead_hours: int) -> m.Delivery:
        n = db.query(m.Delivery).count() + 1
        while db.get(m.Delivery, f"DEL-{n:03d}"):
            n += 1
        d = m.Delivery(id=f"DEL-{n:03d}", component_id=comp.id, supplier_id=comp.supplier_id, quantity=max(1, quantity),
                       eta_hour=now_hour(db) + lead_hours, status="ON_TIME", is_replacement=True)
        db.add(d)
        return d

    def supplier_report(self, db, ref: str | None = None) -> list[dict]:
        out = []
        for s in db.query(m.Supplier).order_by(m.Supplier.id).all():
            if ref and ref.lower() not in s.name.lower() and ref.upper() != s.id:
                continue
            ds = (db.query(m.Delivery).filter(m.Delivery.supplier_id == s.id, m.Delivery.status.in_(OPEN_DELIVERY)).all())
            out.append({"id": s.id, "name": s.name, "reliability": s.reliability, "lead_time_days": s.lead_time_days,
                        "open_deliveries": [{"id": d.id, "component_id": d.component_id, "component": d.component.name,
                                             "eta_hour": d.eta_hour, "status": d.status, "delay_hours": d.delay_hours} for d in ds]})
        return out

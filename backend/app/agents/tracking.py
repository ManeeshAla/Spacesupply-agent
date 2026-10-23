"""Component Tracking Agent: lifecycle state machine, locations and event history."""
from __future__ import annotations

from .. import models as m
from ..lifecycle import EVENT_NAME, GROUP_OF, INSPECTION_HOURS, LOCATION
from .base import log, now_hour

NAME = "Tracking Agent"


class TrackingAgent:
    # ------------------------------------------------------------------ queries
    def find_component(self, db, ref: str):
        ref = ref.strip().upper().replace(" ", "")
        if ref.startswith("CMP") and "-" not in ref:
            ref = "CMP-" + ref[3:]
        if ref.startswith("CMP-"):
            ref = "CMP-" + ref[4:].zfill(3)
        return db.get(m.Component, ref)

    def history(self, db, cid: str) -> list[m.ComponentEvent]:
        return (db.query(m.ComponentEvent).filter(m.ComponentEvent.component_id == cid)
                .order_by(m.ComponentEvent.hour, m.ComponentEvent.id).all())

    def locate(self, db, cid: str) -> dict:
        c = db.get(m.Component, cid)
        open_del = (db.query(m.Delivery).filter(m.Delivery.component_id == cid, m.Delivery.status.in_(["ON_TIME", "DELAYED", "ARRIVED"]))
                    .order_by(m.Delivery.eta_hour).first())
        return {"id": c.id, "name": c.name, "status": c.status, "location": c.location,
                "inspection_status": c.inspection_status, "quantity": c.quantity, "required": c.required_quantity,
                "stage_id": c.stage_id, "supplier": c.supplier.name, "criticality": c.criticality,
                "ready_in_hours": max(0, c.expected_ready_hour - now_hour(db)) if c.status not in m.USABLE else 0,
                "delivery": None if not open_del else {"id": open_del.id, "eta_hour": open_del.eta_hour, "eta_in": open_del.eta_hour - now_hour(db), "status": open_del.status,
                                                        "delay_hours": open_del.delay_hours, "quantity": open_del.quantity}}

    def component_groups(self, db) -> dict:
        groups = {"available": [0, 0], "in_inspection": [0, 0], "in_assembly": [0, 0],
                  "installed": [0, 0], "rejected": [0, 0], "on_order": [0, 0], "delayed": [0, 0]}
        delayed_ids = {d.component_id for d in db.query(m.Delivery).filter(m.Delivery.status == "DELAYED")}
        open_qty: dict[str, int] = {}
        for d in db.query(m.Delivery).filter(m.Delivery.status != "CLEARED"):
            open_qty[d.component_id] = open_qty.get(d.component_id, 0) + d.quantity
        for c in db.query(m.Component).all():
            g = GROUP_OF[c.status]
            if c.id in delayed_ids and c.status == m.ORDERED:
                g = "delayed"
            groups[g][0] += 1
            groups[g][1] += c.quantity + open_qty.get(c.id, 0)
        return {k: {"lots": v[0], "units": v[1]} for k, v in groups.items()}

    def stage_progress(self, db) -> list[dict]:
        now = now_hour(db)
        out = []
        for st in db.query(m.Stage).order_by(m.Stage.id).all():
            tasks = db.query(m.Task).filter(m.Task.stage_id == st.id).all()
            total = sum(t.duration for t in tasks) or 1
            done = 0.0
            for t in tasks:
                if t.status == m.T_COMPLETED:
                    done += t.duration
                elif t.status == m.T_IN_PROGRESS:
                    span = max(1, (t.end_hour or now) - (t.start_hour or now))
                    done += t.duration * min(1.0, max(0.0, (now - (t.start_hour or now)) / span))
            pct = round(100 * done / total)
            n_done = sum(1 for t in tasks if t.status == m.T_COMPLETED)
            status = "Completed" if n_done == len(tasks) else ("In Progress" if (done > 0 or any(t.status == m.T_IN_PROGRESS for t in tasks)) else "Pending")
            out.append({"id": st.id, "name": st.name, "short_name": st.short_name, "progress": pct, "status": status,
                        "tasks_total": len(tasks), "tasks_done": n_done,
                        "tasks_active": sum(1 for t in tasks if t.status == m.T_IN_PROGRESS)})
        return out

    # ------------------------------------------------------------------ commands
    def transition(self, db, comp: m.Component, new_status: str, note: str = "", hour: int | None = None,
                   location: str | None = None) -> m.ComponentEvent:
        if new_status not in m.ALLOWED_TRANSITIONS.get(comp.status, set()):
            raise ValueError(f"Illegal transition {comp.status} -> {new_status} for {comp.id}")
        hour = now_hour(db) if hour is None else hour
        old = comp.status
        comp.status = new_status
        if location:
            comp.location = location
        elif new_status == m.INSTALLED:
            comp.location = f"Installed – Stage {comp.stage_id}"
        else:
            comp.location = LOCATION[new_status]
        comp.inspection_status = {m.IN_INSPECTION: "IN_PROGRESS", m.REJECTED: "FAILED", m.ORDERED: "PENDING",
                                  m.RECEIVED: "PENDING", m.INSPECTION_PENDING: "PENDING"}.get(new_status, "PASSED")
        ev = m.ComponentEvent(component_id=comp.id, hour=hour, event_type=EVENT_NAME[new_status], from_status=old,
                              to_status=new_status, location=comp.location, note=note)
        db.add(ev)
        return ev

    def reject(self, db, cid: str, replacement_hours: int = 36, reason: str = "Failed inspection") -> dict:
        comp = db.get(m.Component, cid)
        if comp is None:
            raise ValueError(f"Unknown component {cid}")
        now = now_hour(db)
        if comp.status not in (m.IN_INSPECTION, m.INSPECTION_PENDING, m.RECEIVED, m.APPROVED, m.IN_WAREHOUSE):
            raise ValueError(f"{cid} is {comp.status}; only components that are in or after inspection can be rejected")
        # walk to IN_INSPECTION first so the history stays legal
        if comp.status == m.RECEIVED:
            self.transition(db, comp, m.INSPECTION_PENDING, hour=now)
        if comp.status == m.INSPECTION_PENDING:
            self.transition(db, comp, m.IN_INSPECTION, hour=now)
        if comp.status == m.APPROVED or comp.status == m.IN_WAREHOUSE:
            # a defect found after clearance: pull back into quarantine
            old = comp.status
            comp.status = m.IN_INSPECTION
            db.add(m.ComponentEvent(component_id=cid, hour=now, event_type="RE_INSPECTION", from_status=old,
                                    to_status=m.IN_INSPECTION, location=LOCATION[m.IN_INSPECTION], note="Defect found after clearance"))
        self.transition(db, comp, m.REJECTED, note=reason, hour=now)
        lost = comp.quantity
        comp.quantity = 0
        from .supply import SupplyAgent
        delivery = SupplyAgent().order_replacement(db, comp, lost or comp.required_quantity, replacement_hours)
        comp.expected_ready_hour = delivery.eta_hour + INSPECTION_HOURS
        log(db, NAME, f"{cid} ({comp.name}) rejected: {reason}. Replacement {delivery.id} due in {replacement_hours}h.")
        return {"component": cid, "replacement_delivery": delivery.id, "eta_hour": delivery.eta_hour}

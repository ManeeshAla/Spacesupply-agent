"""Tools the supervisor agent may call.

Every tool is a thin wrapper over a method that already exists on one of the specialist
agents (tracking / supply / scheduling / monitoring) or on the engine, so the LLM never
touches the database directly and never invents a fact: it can only report what a tool
returned.

Three kinds of tool:
  * read tools        - run immediately, never change state.
  * action tools      - change the simulation. With CONFIRM_ACTIONS on (the default) they
                        do NOT run: they register a pending action and the UI asks the user
                        to confirm first.
  * ui tools          - return a command that moves the dashboard (open a page / a drawer).

Each tool returns a plain dict. `ui` and `blocks` keys are stripped out by the supervisor
and forwarded to the frontend; the rest is what the model gets to read.
"""
from __future__ import annotations

import uuid
from contextlib import nullcontext
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

from .. import models as m
from ..agents.base import fmt, now_hour
from ..engine import engine as eng
from ..microlm.entities import best, norm_cmp

PAGES = ("dashboard", "components", "inventory", "schedule", "tracking", "alerts", "agents", "reports")


# ---------------------------------------------------------------- context
@dataclass
class ToolCtx:
    """Everything a tool needs: the session, the write lock and the UI side-channel."""
    db: Any
    lock: Any = None                              # threading.RLock from main, or None in tests
    confirm: bool = True                          # ask before simulation/state changes
    events: list[dict] = field(default_factory=list)   # ui / block / pending events for SSE
    pending: dict | None = None                   # the action waiting for confirmation
    called: list[dict] = field(default_factory=list)   # trace of tool calls (for the UI)
    sources: list[str] = field(default_factory=list)   # raw tool output, for the grounding guard
    sink: Callable[[dict], None] | None = None    # live event sink (SSE); None = collect only
    on_token: Callable[[str], None] = lambda _t: None   # text delta from the model
    on_note: Callable[[str], None] = lambda _t: None    # retry / model-switch notice
    model_used: str | None = None

    def guard(self):
        return self.lock if self.lock is not None else nullcontext()

    def emit(self, kind: str, data: dict) -> None:
        ev = {"type": kind, **data}
        self.events.append(ev)
        if self.sink:
            self.sink(ev)


# ---------------------------------------------------------------- registry
@dataclass
class ToolSpec:
    name: str
    description: str
    args: type[BaseModel]
    fn: Callable[..., dict]
    write: bool = False
    confirm_text: Callable[[dict], str] | None = None


REGISTRY: dict[str, ToolSpec] = {}


def tool(name: str, description: str, args: type[BaseModel], write: bool = False,
         confirm_text: Callable[[dict], str] | None = None):
    def deco(fn):
        REGISTRY[name] = ToolSpec(name, description, args, fn, write, confirm_text)
        return fn
    return deco


# ---------------------------------------------------------------- lookup helpers
def _component(db, ref: str) -> m.Component:
    """Find a component by id ('CMP-21', 'cmp21') or by name ('fuel pump')."""
    ref = (ref or "").strip()
    if not ref:
        raise LookupError("No component given.")
    c = eng.tracking.find_component(db, ref)
    if c:
        return c
    cid = norm_cmp(ref)
    if cid and db.get(m.Component, cid):
        return db.get(m.Component, cid)
    hit = best(ref, {x.id: [x.name] for x in db.query(m.Component).all()}, 0.6)
    if hit:
        return db.get(m.Component, hit[0])
    raise LookupError(f"No component matches '{ref}'. Component ids look like CMP-021.")


def _task(db, ref: str) -> m.Task:
    import re
    ref = (ref or "").strip()
    if not ref:
        raise LookupError("No task given.")
    mm = re.search(r"t\s*-?\s*(\d{1,3})", ref.lower())
    if mm:
        t = db.get(m.Task, f"T-{int(mm.group(1)):03d}")
        if t:
            return t
    hit = best(ref, {x.id: [x.name] for x in db.query(m.Task).all()}, 0.6)
    if hit:
        return db.get(m.Task, hit[0])
    raise LookupError(f"No task matches '{ref}'. Task ids look like T-012.")


def _workstation(db, ref: str) -> m.Workstation:
    import re
    ref = (ref or "").strip()
    mm = re.search(r"ws\s*-?\s*(\d{1,2})", ref.lower())
    if mm:
        w = db.get(m.Workstation, f"WS-{int(mm.group(1)):02d}")
        if w:
            return w
    hit = best(ref, {w.id: [w.name, w.ws_type] for w in db.query(m.Workstation).all()}, 0.55)
    if hit:
        return db.get(m.Workstation, hit[0])
    raise LookupError(f"No workstation matches '{ref}'. Workstation ids look like WS-04.")


def _when(db, hour: int | None) -> dict | None:
    if hour is None:
        return None
    return {"hour": hour, "time": fmt(db, hour), "in_hours": hour - now_hour(db)}


def _stage_of_alert(db, a: m.Alert) -> int | None:
    if a.task_id:
        t = db.get(m.Task, a.task_id)
        if t:
            return t.stage_id
    if a.component_id:
        c = db.get(m.Component, a.component_id)
        if c:
            return c.stage_id
    return None


# ================================================================ READ TOOLS
class ComponentArgs(BaseModel):
    component: str = Field(description="Component id such as CMP-021, or its name such as 'fuel pump'.")


@tool("get_component", "Full state of one component lot: lifecycle status, physical location, inspection, "
      "quantity on hand vs required, supplier, delivery ETA, and which tasks use it. Use this for "
      "'where is X', 'what is the status of X', 'is X here yet'.", ComponentArgs)
def get_component(ctx: ToolCtx, component: str) -> dict:
    db = ctx.db
    c = _component(db, component)
    loc = eng.tracking.locate(db, c.id)
    users = [{"task_id": t.id, "name": t.name, "status": t.status}
             for t in eng.supply.tasks_needing(db, c.id, pending_only=False)]
    d = loc.get("delivery")
    return {
        "id": c.id, "name": c.name, "category": c.category, "stage_id": c.stage_id,
        "status": c.status, "location": c.location, "inspection_status": c.inspection_status,
        "criticality": c.criticality, "quantity_on_hand": c.quantity, "quantity_required": c.required_quantity,
        "supplier": c.supplier.name, "usable_now": c.status in m.USABLE,
        "ready_in_hours": loc.get("ready_in_hours"),
        "delivery": {"id": d["id"], "status": d["status"], "delay_hours": d["delay_hours"],
                     "quantity": d["quantity"], "eta": _when(db, d["eta_hour"])} if d else None,
        "used_by_tasks": users,
        "ui": {"action": "open_component", "component_id": c.id},
    }


@tool("get_component_history", "Chronological lifecycle events for one component (ordered, received, "
      "inspected, moved to warehouse/bay, installed, rejected). Use for 'what happened to X'.", ComponentArgs)
def get_component_history(ctx: ToolCtx, component: str) -> dict:
    db = ctx.db
    c = _component(db, component)
    ev = eng.tracking.history(db, c.id)
    return {"id": c.id, "name": c.name, "events": [
        {"time": fmt(db, e.hour), "hour": e.hour, "event": e.event_type, "from": e.from_status,
         "to": e.to_status, "location": e.location,
         "note": "" if e.note == "Seed history" else e.note} for e in ev[-14:]],
        "ui": {"action": "open_component", "component_id": c.id}}


class ListComponentsArgs(BaseModel):
    status: str | None = Field(None, description="Lifecycle status filter, e.g. ORDERED, IN_INSPECTION, IN_WAREHOUSE, INSTALLED, REJECTED.")
    stage: int | None = Field(None, description="Vehicle stage 1-4.")
    query: str | None = Field(None, description="Free-text match on id, name or location.")


@tool("list_components", "List component lots, optionally filtered by lifecycle status, stage or text. "
      "Use for 'how many components are in inspection', 'show rejected parts'.", ListComponentsArgs)
def list_components(ctx: ToolCtx, status: str | None = None, stage: int | None = None,
                    query: str | None = None) -> dict:
    db = ctx.db
    q = db.query(m.Component)
    if status:
        q = q.filter(m.Component.status == status.upper().replace(" ", "_"))
    if stage:
        q = q.filter(m.Component.stage_id == stage)
    rows = q.order_by(m.Component.id).all()
    if query:
        ql = query.lower()
        rows = [c for c in rows if ql in c.id.lower() or ql in c.name.lower() or ql in c.location.lower()]
    out = [{"id": c.id, "name": c.name, "status": c.status, "location": c.location, "stage_id": c.stage_id,
            "on_hand": c.quantity, "required": c.required_quantity} for c in rows[:25]]
    return {"count": len(rows), "showing": len(out), "components": out,
            "ui": {"action": "navigate", "page": "components",
                   "filters": {"stage": stage or 0, "query": query or "", "status": (status or "").upper()}}}


class StageArgs(BaseModel):
    stage: int | None = Field(None, description="Vehicle stage 1-4. Omit for the whole vehicle.")


@tool("get_inventory", "Inventory roll-up: how many component lots are sufficient / low / critical / on order, "
      "plus the biggest shortages. Use for 'how is inventory', 'what are we short of'.", StageArgs)
def get_inventory(ctx: ToolCtx, stage: int | None = None) -> dict:
    db = ctx.db
    rows = eng.supply.shortages(db, stage_id=stage)
    return {"scope": f"Stage {stage}" if stage else "whole vehicle",
            "summary": eng.supply.summary(db),
            "short_lots": len(rows),
            "top_shortages": [{"id": r["id"], "name": r["name"], "required": r["required"],
                               "available": r["available"], "shortage": r["shortage"], "class": r["class"],
                               "status": r["status"], "incoming": r["incoming"],
                               "next_eta": _when(db, r["next_eta_hour"]), "delayed": r["delayed"],
                               "supplier": r["supplier"]} for r in rows[:8]],
            "ui": {"action": "navigate", "page": "inventory"}}


class ShortageArgs(BaseModel):
    stage: int | None = Field(None, description="Vehicle stage 1-4.")
    task: str | None = Field(None, description="Task id or name, to check only what that task needs.")
    component: str | None = Field(None, description="One component id or name.")


@tool("get_shortages", "Components that are short of the quantity required, with the tasks they block. "
      "Use for 'are we missing anything for engine assembly', 'what is blocking stage 2'.", ShortageArgs)
def get_shortages(ctx: ToolCtx, stage: int | None = None, task: str | None = None,
                  component: str | None = None) -> dict:
    db = ctx.db
    if component:
        c = _component(db, component)
        rows = [r for r in eng.supply.inventory_rows(db) if r["id"] == c.id]
        scope = f"{c.id} {c.name}"
    elif task:
        t = _task(db, task)
        rows = eng.supply.shortages(db, task_id=t.id)
        scope = f"{t.id} {t.name}"
    else:
        rows = eng.supply.shortages(db, stage_id=stage)
        scope = f"Stage {stage}" if stage else "whole vehicle"
    return {"scope": scope, "count": len(rows),
            "shortages": [{"id": r["id"], "name": r["name"], "required": r["required"], "available": r["available"],
                           "shortage": r["shortage"], "class": r["class"], "status": r["status"],
                           "next_eta": _when(db, r["next_eta_hour"]), "delayed": r["delayed"],
                           "affected_tasks": r.get("affected_tasks", [])[:5]} for r in rows[:10]]}


class SupplierArgs(BaseModel):
    supplier: str | None = Field(None, description="Supplier name, e.g. 'Orbital Forge'.")
    component: str | None = Field(None, description="Component id or name, to get that lot's supplier.")


@tool("get_supplier", "Supplier details (reliability, lead time) and their open deliveries. "
      "Use for 'who supplies X', 'which supplier is late'.", SupplierArgs)
def get_supplier(ctx: ToolCtx, supplier: str | None = None, component: str | None = None) -> dict:
    db = ctx.db
    if component:
        c = _component(db, component)
        ds = eng.supply.open_deliveries(db, c.id)
        return {"component": c.id, "component_name": c.name, "supplier": c.supplier.name,
                "reliability": round(c.supplier.reliability, 2), "lead_time_days": c.supplier.lead_time_days,
                "open_deliveries": [{"id": d.id, "quantity": d.quantity, "eta": _when(db, d.eta_hour),
                                     "status": d.status, "delay_hours": d.delay_hours} for d in ds]}
    rep = eng.supply.supplier_report(db, supplier)
    return {"suppliers": [{"id": s["id"], "name": s["name"], "reliability": round(s["reliability"], 2),
                           "lead_time_days": s["lead_time_days"],
                           "open_deliveries": [{"id": d["id"], "component_id": d["component_id"],
                                                "component": d["component"], "eta": _when(db, d["eta_hour"]),
                                                "delay_hours": d["delay_hours"]} for d in s["open_deliveries"][:6]]}
                          for s in rep[:6]]}


class ScheduleArgs(BaseModel):
    stage: int | None = Field(None, description="Only tasks of this vehicle stage (1-4).")
    workstation: str | None = Field(None, description="Only tasks on this workstation, e.g. WS-04.")
    task: str | None = Field(None, description="One task id or name.")
    window_hours: int | None = Field(None, description="Only tasks starting within this many hours from now (e.g. 24 for 'today').")
    late_only: bool = Field(False, description="Only tasks that are late or have moved.")


@tool("get_schedule", "The current optimised assembly schedule: task, workstation, planned start/end, "
      "lateness and the binding constraint. Use for 'show the schedule', 'what is running today', "
      "'what is planned on WS-04'.", ScheduleArgs)
def get_schedule(ctx: ToolCtx, stage: int | None = None, workstation: str | None = None,
                 task: str | None = None, window_hours: int | None = None, late_only: bool = False) -> dict:
    db = ctx.db
    rows = eng.scheduling.schedule_rows(db)
    now = now_hour(db)
    ver = eng.scheduling.current_version(db)
    title = "whole vehicle"
    ws_id = None
    if task:
        t = _task(db, task)
        rows, title = [r for r in rows if r["id"] == t.id], f"{t.id} {t.name}"
    elif workstation:
        w = _workstation(db, workstation)
        ws_id = w.id
        rows = [r for r in rows if r["workstation"] == w.id and r["status"] != m.T_COMPLETED]
        title = f"{w.id} {w.name}"
    elif stage:
        rows = [r for r in rows if r["stage_id"] == stage and r["status"] != m.T_COMPLETED]
        title = f"Stage {stage}"
    if window_hours:
        rows = [r for r in rows if r["status"] == m.T_IN_PROGRESS or
                (r["start_hour"] is not None and 0 <= r["start_hour"] - now <= window_hours)]
        title += f", next {window_hours}h"
    if late_only:
        rows = [r for r in rows if r["late_hours"] > 0 or r["shift_hours"] != 0]
    rows.sort(key=lambda r: (r["start_hour"] if r["start_hour"] is not None else 10 ** 6))
    out = [{"task_id": r["id"], "name": r["name"], "stage_id": r["stage_id"], "status": r["status"],
            "workstation": r["workstation"], "start": _when(db, r["start_hour"]), "end": _when(db, r["end_hour"]),
            "duration_hours": r["duration"], "priority": r["priority"], "late_hours": r["late_hours"],
            "moved_hours": r["shift_hours"], "reason": r["reason_text"]} for r in rows[:14]]
    ui = {"action": "navigate", "page": "schedule",
          "filters": {"schedule": str(stage) if stage else ("LATE" if late_only else "ACTIVE")}}
    return {"scope": title, "now": fmt(db, now), "count": len(rows), "showing": len(out),
            "plan_version": ver.id if ver else None, "algorithm": ver.algorithm if ver else None,
            "tasks": out, "ui": ui,
            "blocks": [{"type": "table", "title": f"Schedule – {title}",
                        "columns": ["Task", "Name", "Workstation", "Starts", "Late"],
                        "rows": [[r["task_id"], r["name"], r["workstation"] or "-",
                                  (r["start"] or {}).get("time", "-"),
                                  f"{r['late_hours']}h" if r["late_hours"] else "-"] for r in out[:8]]}] if out else []}


class TaskArgs(BaseModel):
    task: str = Field(description="Task id such as T-012, or its name such as 'engine assembly'.")


@tool("explain_task", "Why one task sits where it does: how far it moved from the original plan, whether it "
      "will miss its deadline, and the chain of binding constraints (waiting for a component / a predecessor "
      "/ a workstation). Use for 'why is X late', 'why did X move'.", TaskArgs)
def explain_task(ctx: ToolCtx, task: str) -> dict:
    db = ctx.db
    t = _task(db, task)
    # a task that has already started or finished gets a reduced explanation (no binding
    # constraint to trace), so every optional key is read defensively
    ex = eng.scheduling.explain_task(db, t.id)
    rd = eng.scheduling.task_readiness(db, t.id)
    return {"task_id": ex["task_id"], "name": ex["name"], "status": ex["status"],
            "planned_start": _when(db, ex.get("planned_start_hour")),
            "planned_end": _when(db, ex.get("planned_end_hour")),
            "deadline": _when(db, ex["deadline_hour"]), "workstation": ex.get("workstation"),
            "moved_hours_vs_original": ex.get("shift_hours", 0),
            "original_start": _when(db, ex.get("original_start_hour")),
            "late_hours": ex.get("late_hours", 0), "reason_type": ex.get("reason_type"),
            "reason": ex.get("reason"), "why_chain": ex.get("chain", []),
            "can_start_now": rd["can_start_now"],
            "blockers": [{"type": b["type"], "ref": b["ref"], "text": b["text"]} for b in rd["blockers"][:6]],
            "ui": {"action": "open_task", "task_id": ex["task_id"]}}


class EmptyArgs(BaseModel):
    pass


@tool("get_delayed_tasks", "Every task that has slipped against the original plan or is projected past its "
      "deadline, plus delayed deliveries. Use for 'what is delayed', 'are we behind'.", EmptyArgs)
def get_delayed_tasks(ctx: ToolCtx) -> dict:
    db = ctx.db
    rows = eng.scheduling.delayed_tasks(db)
    dd = db.query(m.Delivery).filter(m.Delivery.status == "DELAYED").all()
    return {"delayed_task_count": len(rows), "delayed_delivery_count": len(dd),
            "tasks": [{"task_id": r["id"], "name": r["name"], "stage_id": r["stage_id"],
                       "moved_hours": r["shift_hours"], "late_hours": r["late_hours"],
                       "start": _when(db, r["start_hour"]), "reason": r["reason_text"]} for r in rows[:10]],
            "deliveries": [{"id": d.id, "component_id": d.component_id, "component": d.component.name,
                            "supplier": d.supplier.name, "delay_hours": d.delay_hours,
                            "eta": _when(db, d.eta_hour)} for d in dd[:8]],
            "ui": {"action": "navigate", "page": "schedule", "filters": {"schedule": "LATE"}}}


class AlertArgs(BaseModel):
    status: str | None = Field(None, description="OPEN, ACKNOWLEDGED, RESOLVED or ALL. Defaults to OPEN.")
    severity: str | None = Field(None, description="CRITICAL, WARNING or INFO.")
    stage: int | None = Field(None, description="Only alerts about tasks/components of this stage (1-4).")


@tool("get_alerts", "Alerts raised by the Monitoring Agent (delivery delays, rejected components, inspection "
      "backlog, workstation down, maintenance due, projected lateness). Use for 'show alerts', "
      "'any critical problems', 'alerts for stage 3'.", AlertArgs)
def get_alerts(ctx: ToolCtx, status: str | None = None, severity: str | None = None,
               stage: int | None = None) -> dict:
    db = ctx.db
    want = (status or "OPEN").upper()
    q = db.query(m.Alert)
    if want != "ALL":
        q = q.filter(m.Alert.status == want)
    if severity:
        q = q.filter(m.Alert.severity == severity.upper())
    rows = q.order_by(m.Alert.id.desc()).limit(200).all()
    if stage:
        rows = [a for a in rows if _stage_of_alert(db, a) == stage]
    rank = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
    rows.sort(key=lambda a: (rank[a.severity], -a.id))
    counts = {s: sum(1 for a in rows if a.severity == s) for s in rank}
    return {"scope": {"status": want, "severity": severity, "stage": stage},
            "count": len(rows), "counts_by_severity": counts,
            "alerts": [{"id": a.id, "severity": a.severity, "category": a.category, "title": a.title,
                        "message": a.message, "task_id": a.task_id, "component_id": a.component_id,
                        "stage_id": _stage_of_alert(db, a), "status": a.status,
                        "raised": fmt(db, a.created_hour)} for a in rows[:10]],
            "ui": {"action": "navigate", "page": "alerts",
                   "filters": {"alertStatus": want, "alertSeverity": (severity or "ALL").upper(),
                               "alertStage": stage or 0}}}


@tool("get_stage_progress", "Assembly progress per vehicle stage: percent complete, tasks done / running, "
      "and the projected launch-readiness date. Use for 'how is stage 2 going', 'overall progress'.", StageArgs)
def get_stage_progress(ctx: ToolCtx, stage: int | None = None) -> dict:
    db = ctx.db
    stages = eng.tracking.stage_progress(db)
    sel = [s for s in stages if stage is None or s["id"] == stage]
    k = eng._kpis(db)
    return {"stages": sel, "launch_readiness": k["launch_readiness"],
            "launch_readiness_late_hours": k["launch_readiness_late_hours"],
            "ui": {"action": "navigate", "page": "tracking"}}


class DeliveryArgs(BaseModel):
    component: str | None = Field(None, description="Only deliveries for this component id or name.")


@tool("get_deliveries", "Deliveries that have not been cleared yet, with ETA and delay. "
      "Use for 'what is arriving', 'when does X arrive'.", DeliveryArgs)
def get_deliveries(ctx: ToolCtx, component: str | None = None) -> dict:
    db = ctx.db
    if component:
        c = _component(db, component)
        ds = eng.supply.open_deliveries(db, c.id)
    else:
        ds = (db.query(m.Delivery).filter(m.Delivery.status.in_(["ON_TIME", "DELAYED"]))
              .order_by(m.Delivery.eta_hour).limit(12).all())
    return {"count": len(ds),
            "deliveries": [{"id": d.id, "component_id": d.component_id, "component": d.component.name,
                            "supplier": d.supplier.name, "quantity": d.quantity, "status": d.status,
                            "delay_hours": d.delay_hours, "is_replacement": d.is_replacement,
                            "eta": _when(db, d.eta_hour)} for d in ds]}


class ReadinessArgs(BaseModel):
    task: str | None = Field(None, description="Task id or name.")
    stage: int | None = Field(None, description="Vehicle stage 1-4.")


@tool("get_task_readiness", "Whether a task (or a whole stage) can start right now, and if not, exactly what "
      "blocks it. Combines the Tracking, Supply and Scheduling agents. Use for 'is stage 2 ready', "
      "'can engine assembly start'.", ReadinessArgs)
def get_task_readiness(ctx: ToolCtx, task: str | None = None, stage: int | None = None) -> dict:
    db = ctx.db
    if task:
        t = _task(db, task)
        # completed / in-progress tasks come back without the planning fields
        rd = eng.scheduling.task_readiness(db, t.id)
        return {"kind": "task", "task_id": rd["task_id"], "name": rd["name"], "status": rd["status"],
                "can_start_now": rd["can_start_now"], "summary": rd["summary"],
                "planned_start": _when(db, rd.get("planned_start_hour")),
                "planned_workstation": rd.get("planned_workstation"),
                "blockers": [{"type": b["type"], "ref": b["ref"], "text": b["text"],
                              "eta_hours": b.get("eta_hours")} for b in rd["blockers"][:8]],
                "components": rd["components"][:10],
                "ui": {"action": "open_task", "task_id": rd["task_id"]}}
    if stage:
        rd = eng.scheduling.stage_readiness(db, stage)
        return {"kind": "stage", "stage_id": rd["stage_id"], "stage": rd["stage"], "ready": rd["ready"],
                "complete": rd.get("complete", False), "summary": rd["summary"],
                "eligible_tasks": [{"task_id": f["task_id"], "name": f["name"],
                                    "planned_workstation": f.get("planned_workstation"),
                                    "planned_start": _when(db, f.get("planned_start_hour"))}
                                   for f in rd["frontier"][:6]],
                "blockers": [{"type": b["type"], "ref": b["ref"], "text": b["text"],
                              "task_id": b.get("task_id")} for b in rd["blockers"][:8]]}
    raise LookupError("Give either a task or a stage to check readiness for.")


@tool("compare_schedulers", "Run all four scheduling algorithms (FCFS, PRIORITY, GA, OR-Tools CP-SAT) on the "
      "current plant state and compare makespan, tardy tasks and objective. Takes a few seconds. "
      "Use for 'which algorithm is best', 'compare the schedulers'.", EmptyArgs)
def compare_schedulers(ctx: ToolCtx) -> dict:
    with ctx.guard():
        res = eng.scheduling.compare(ctx.db)
    return {"objective": "10 x priority-weighted tardiness + makespan (lower is better)",
            "results": res, "ui": {"action": "navigate", "page": "reports"}}


@tool("get_plant_status", "One-shot overview: system status, open alert counts, tasks running, components by "
      "lifecycle group, inventory roll-up, projected launch readiness, and whether live mode is running. "
      "Use for 'how are things', 'give me a status update', 'what is the situation'.", EmptyArgs)
def get_plant_status(ctx: ToolCtx) -> dict:
    db = ctx.db
    from ..live import live
    d = eng.dashboard(db)
    st = live.state()
    return {"now": d["now_iso"], "system_status": d["system_status"], "kpis": d["kpis"],
            "stages": [{"id": s["id"], "name": s["short_name"], "progress": s["progress"],
                        "status": s["status"]} for s in d["stages"]],
            "inventory": d["inventory"], "components_by_group": d["component_status"],
            "launch": {"readiness": d["launch"]["launch_readiness"],
                       "late_hours": d["launch"]["launch_readiness_late_hours"],
                       "makespan": d["launch"]["makespan"], "tardy_tasks": d["launch"]["tardy_tasks"]},
            "live_mode": {"running": st["running"], "speed": st["speed"], "random_events": st["chaos"]},
            "open_alerts": [{"id": a["id"], "severity": a["severity"], "title": a["title"]} for a in d["alerts"]]}


@tool("get_live_mode", "Live simulation state: running or paused, speed multiplier, whether random disruptions "
      "are on, and the most recent feed lines.", EmptyArgs)
def get_live_mode(ctx: ToolCtx) -> dict:
    from ..live import live
    st = live.state()
    return {"running": st["running"], "speed": st["speed"], "random_events": st["chaos"],
            "seconds_per_plant_hour": st["seconds_per_hour"],
            "recent_feed": [{"kind": f["kind"], "severity": f["severity"], "text": f["text"],
                             "time": f["time"]} for f in st["feed"][-8:]]}


@tool("get_agent_messages", "Recent messages the agents sent each other on the message bus (supplier.delay, "
      "schedule.replanned, alerts.scanned ...). Use for 'what did the agents do', 'show agent communication'.",
      EmptyArgs)
def get_agent_messages(ctx: ToolCtx) -> dict:
    from .. import bus as bus_mod
    rows = bus_mod.recent(ctx.db, 0, 20)
    return {"count": len(rows),
            "messages": [{"topic": r["topic"], "from": r["sender"], "to": r["recipient"],
                          "summary": r["summary"], "time": r["time"],
                          "correlation_id": r["correlation_id"]} for r in rows],
            "ui": {"action": "navigate", "page": "agents"}}


# ================================================================ UI TOOL
class ShowArgs(BaseModel):
    page: Literal["dashboard", "components", "inventory", "schedule", "tracking", "alerts", "agents", "reports"] = \
        Field(description="Which dashboard page to open.")
    stage: int | None = Field(None, description="Pre-set a stage filter (1-4) on that page.")
    component: str | None = Field(None, description="Also open this component's detail drawer.")
    task: str | None = Field(None, description="Also open this task's detail drawer.")
    severity: str | None = Field(None, description="On the alerts page: CRITICAL, WARNING or INFO.")


@tool("show_dashboard", "Move the user's dashboard: open a page, pre-set its filter, or open a component/task "
      "drawer. Use when the user says 'show me', 'open', 'take me to'. Call a read tool as well if they also "
      "asked a question.", ShowArgs)
def show_dashboard(ctx: ToolCtx, page: str, stage: int | None = None, component: str | None = None,
                   task: str | None = None, severity: str | None = None) -> dict:
    db = ctx.db
    filters: dict = {}
    if stage:
        filters["stage"] = stage
        if page == "schedule":
            filters["schedule"] = str(stage)
        if page == "alerts":
            filters["alertStage"] = stage
    if severity and page == "alerts":
        filters["alertSeverity"] = severity.upper()
    ui: dict = {"action": "navigate", "page": page, "filters": filters}
    opened = {}
    if component:
        c = _component(db, component)
        ui["component_id"] = c.id
        opened["component"] = c.id
    if task:
        t = _task(db, task)
        ui["task_id"] = t.id
        opened["task"] = t.id
    return {"opened": {"page": page, **({"filters": filters} if filters else {}), **opened}, "ui": ui}


# ================================================================ ACTION TOOLS
class DelayArgs(BaseModel):
    component: str = Field(description="Component id or name whose delivery is delayed.")
    hours: int = Field(description="How many hours late (1-240).")
    reason: str | None = Field(None, description="Short reason, e.g. 'customs hold'.")


@tool("delay_delivery", "SIMULATION: register a supplier delay on a component's open delivery. The Supply "
      "Agent publishes it, the Scheduling Agent re-plans with CP-SAT and the Monitoring Agent raises alerts.",
      DelayArgs, write=True,
      confirm_text=lambda a: f"Delay {a['component']}'s delivery by {a['hours']}h"
                             + (f" ({a['reason']})" if a.get("reason") else "")
                             + ". This re-plans the whole schedule.")
def delay_delivery(ctx: ToolCtx, component: str, hours: int, reason: str | None = None) -> dict:
    db = ctx.db
    c = _component(db, component)
    with ctx.guard():
        res = eng.handle_event(db, {"type": "SUPPLIER_DELAY", "component_id": c.id, "hours": int(hours)})
        _push_live(db, f"Chat: supplier delay {c.id} +{int(hours)}h" + (f" ({reason})" if reason else ""))
    return _event_result(db, res, f"{c.id} ({c.name}) delivery delayed by {int(hours)}h")


class RejectArgs(BaseModel):
    component: str = Field(description="Component id or name to reject. It must be in or past inspection.")
    replacement_hours: int = Field(36, description="Lead time in hours for the replacement delivery.")


@tool("reject_component", "SIMULATION: fail a component in inspection. The Tracking Agent quarantines it and "
      "orders a replacement, then the schedule is re-planned.", RejectArgs, write=True,
      confirm_text=lambda a: f"Reject {a['component']} in inspection and order a replacement "
                             f"(+{a.get('replacement_hours', 36)}h). This re-plans the whole schedule.")
def reject_component(ctx: ToolCtx, component: str, replacement_hours: int = 36) -> dict:
    db = ctx.db
    c = _component(db, component)
    with ctx.guard():
        res = eng.handle_event(db, {"type": "REJECT_COMPONENT", "component_id": c.id,
                                    "replacement_hours": int(replacement_hours)})
        _push_live(db, f"Chat: {c.id} rejected in inspection")
    return _event_result(db, res, f"{c.id} ({c.name}) rejected; replacement ordered")


class WsDownArgs(BaseModel):
    workstation: str = Field(description="Workstation id such as WS-04, or its name.")
    hours: int = Field(description="How many hours it stays out of service (1-240).")


@tool("workstation_down", "SIMULATION: take a workstation out of service for a number of hours, then re-plan.",
      WsDownArgs, write=True,
      confirm_text=lambda a: f"Take {a['workstation']} out of service for {a['hours']}h. "
                             f"This re-plans the whole schedule.")
def workstation_down(ctx: ToolCtx, workstation: str, hours: int) -> dict:
    db = ctx.db
    w = _workstation(db, workstation)
    with ctx.guard():
        res = eng.handle_event(db, {"type": "WORKSTATION_DOWN", "workstation_id": w.id, "hours": int(hours)})
        _push_live(db, f"Chat: {w.id} down for {int(hours)}h")
    return _event_result(db, res, f"{w.id} ({w.name}) down for {int(hours)}h")


class ReplanArgs(BaseModel):
    algorithm: Literal["CPSAT", "GA", "PRIORITY", "FCFS"] = Field(
        "CPSAT", description="CPSAT (OR-Tools, best), GA (genetic algorithm), PRIORITY or FCFS (baselines).")


@tool("replan_schedule", "Re-optimise the assembly schedule with the chosen algorithm and create a new plan "
      "version. Use when the user asks to re-plan / reschedule / re-optimise.", ReplanArgs, write=True,
      confirm_text=lambda a: f"Re-plan the whole schedule with {a.get('algorithm', 'CPSAT')} "
                             f"and make it the active plan.")
def replan_schedule(ctx: ToolCtx, algorithm: str = "CPSAT") -> dict:
    db = ctx.db
    with ctx.guard():
        res = eng.request_replan(db, algorithm.upper(), trigger=f"Chat request ({algorithm.upper()})")
        _push_live(db, f"Chat: re-planned with {algorithm.upper()}")
    met = res.get("metrics") or {}
    return {"action": "replan", "plan_version": res.get("version_id"), "algorithm": res.get("algorithm"),
            "metrics": met, "tasks_moved": len(res.get("changes") or []),
            "changes": [{"task_id": c["task_id"], "name": c["name"], "moved_hours": c["delta_hours"],
                         "reason": c["reason"]} for c in (res.get("changes") or [])[:6]],
            "agent_steps": res.get("steps", []),
            "ui": {"action": "navigate", "page": "schedule"}}


class AdvanceArgs(BaseModel):
    hours: int = Field(description="Plant hours to simulate forward (1-240).")


@tool("advance_time", "SIMULATION: run the plant clock forward. Deliveries arrive, inspections clear, tasks "
      "start and finish, and the plan is re-optimised if anything drifts.", AdvanceArgs, write=True,
      confirm_text=lambda a: f"Advance the simulation clock by {a['hours']}h. "
                             f"Deliveries, inspections and tasks will progress.")
def advance_time(ctx: ToolCtx, hours: int) -> dict:
    db = ctx.db
    with ctx.guard():
        res = eng.advance(db, int(hours))
        _push_live(db, f"Chat: advanced {int(hours)}h")
    return {"action": "advance_time", "from": fmt(db, res["from_hour"]), "to": fmt(db, res["to_hour"]),
            "hours": int(hours), "drift_replans": res["replans"],
            "state_changes": res["changes"][-12:],
            "alerts": {"new": len(res["alerts"]["created"]), "resolved": res["alerts"]["resolved"],
                       "open": res["alerts"]["open"]},
            "launch": {"readiness": res["after"]["launch_readiness"],
                       "late_hours": res["after"]["launch_readiness_late_hours"],
                       "tardy_tasks": res["after"]["tardy_tasks"]}}


class AckArgs(BaseModel):
    alert_id: int = Field(description="Numeric alert id, from get_alerts.")


@tool("acknowledge_alert", "Mark one alert as acknowledged.", AckArgs)
def acknowledge_alert(ctx: ToolCtx, alert_id: int) -> dict:
    db = ctx.db
    with ctx.guard():
        a = eng.monitoring.ack(db, int(alert_id))
        db.commit()
    return {"action": "acknowledge_alert", "id": a.id, "title": a.title, "status": a.status,
            "ui": {"action": "navigate", "page": "alerts", "filters": {"alertStatus": "ALL"}}}


class LiveArgs(BaseModel):
    running: bool | None = Field(None, description="True to play the live simulation, False to pause it.")
    # a plain int, not a Literal: Gemini's schema only accepts string enums
    speed: int | None = Field(None, description="Speed multiplier. Must be exactly 1, 2, 4 or 8.")
    random_events: bool | None = Field(None, description="Turn random disruptions on or off.")


@tool("control_live_mode", "Play, pause, change the speed of, or toggle random disruptions in the live "
      "simulation. Use for 'start live mode', 'pause', 'speed up', 'stop the random failures'.", LiveArgs)
def control_live_mode(ctx: ToolCtx, running: bool | None = None, speed: int | None = None,
                      random_events: bool | None = None) -> dict:
    from ..live import live
    st = live.configure(running, speed, random_events)
    return {"action": "live_mode", "running": st["running"], "speed": st["speed"],
            "random_events": st["chaos"], "seconds_per_plant_hour": st["seconds_per_hour"]}


# ---------------------------------------------------------------- action helpers
def _push_live(db, text: str) -> None:
    from ..live import live
    live.push(db, "DISRUPTION", text, "WARNING")


def _event_result(db, res: dict, headline: str) -> dict:
    """Compact, grounded view of an engine event for the model to report."""
    before, after = res["before"], res["after"]
    return {"action": "simulated_event", "headline": headline, "trigger": res["trigger"],
            "agent_steps": res["steps"], "plan_version": res.get("version_id"),
            "tasks_moved": len(res.get("schedule_changes") or []),
            "schedule_changes": [{"task_id": c["task_id"], "name": c["name"], "moved_hours": c["delta_hours"],
                                  "reason": c["reason"]} for c in (res.get("schedule_changes") or [])[:6]],
            "impact": {"before": {"tardy_tasks": before["tardy_tasks"], "makespan": before["makespan"],
                                  "launch_readiness": before["launch_readiness"]},
                       "after": {"tardy_tasks": after["tardy_tasks"], "makespan": after["makespan"],
                                 "launch_readiness": after["launch_readiness"],
                                 "launch_late_hours": after["launch_readiness_late_hours"]}},
            "ui": {"action": "navigate", "page": "schedule"}}


# ---------------------------------------------------------------- dispatch
def run_tool(ctx: ToolCtx, name: str, args: dict) -> dict:
    """Execute one tool by name. Write tools are gated behind confirmation when enabled."""
    spec = REGISTRY.get(name)
    if spec is None:
        return {"error": f"Unknown tool '{name}'."}
    try:
        parsed = spec.args(**(args or {})).model_dump()
    except Exception as exc:
        return {"error": f"Invalid arguments for {name}: {exc}"}

    if spec.write and ctx.confirm:
        action_id = uuid.uuid4().hex[:10]
        summary = spec.confirm_text(args or {}) if spec.confirm_text else f"Run {name}"
        ctx.pending = {"id": action_id, "tool": name, "args": parsed, "summary": summary}
        ctx.emit("pending", {"action": ctx.pending})
        return {"status": "confirmation_required", "action_id": action_id, "summary": summary,
                "note": "Nothing has changed yet. Tell the user what will happen and that they must press "
                        "Confirm. Do not claim the action was done."}
    return execute(ctx, name, parsed)


def execute(ctx: ToolCtx, name: str, args: dict) -> dict:
    """Run a tool for real (no confirmation gate). Used by run_tool and by /api/chat/confirm."""
    spec = REGISTRY[name]
    try:
        out = spec.fn(ctx, **args)
    except LookupError as exc:
        return {"error": str(exc)}
    except ValueError as exc:
        return {"error": f"{exc}"}
    except Exception as exc:  # a broken tool must not kill the chat
        ctx.db.rollback()
        return {"error": f"{type(exc).__name__}: {exc}"}
    ui = out.pop("ui", None)
    blocks = out.pop("blocks", None)
    if ui:
        ctx.emit("ui", {"command": ui})
    for b in (blocks or []):
        ctx.emit("block", {"block": b})
    return out


def tool_names() -> list[str]:
    return sorted(REGISTRY)


def write_tools() -> list[str]:
    return sorted(n for n, s in REGISTRY.items() if s.write)

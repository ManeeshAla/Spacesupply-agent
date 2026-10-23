"""FastAPI application: REST API for the React dashboard + background supervisor."""
from __future__ import annotations

import asyncio
import json
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import models as m
from .agents.base import fmt, iso, now_hour
from .config import (BENCHMARK_PATH, MICROLM_METRICS, MICROLM_PATH, SUPERVISOR_ENABLED, SUPERVISOR_INTERVAL_S)
from .database import SessionLocal, get_db
from .engine import engine as eng
from .lifecycle import GROUP_OF

LOCK = threading.RLock()   # one writer at a time (SQLite + CP-SAT re-planning)


async def _supervisor():
    while True:
        await asyncio.sleep(SUPERVISOR_INTERVAL_S)
        def cycle():
            with LOCK:
                db = SessionLocal()
                try:
                    eng.supervisor_cycle(db)
                finally:
                    db.close()
        try:
            await asyncio.to_thread(cycle)
        except Exception as exc:  # never let the supervisor die
            print("supervisor error:", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not MICROLM_PATH.exists():
        print("Micro LM checkpoint missing -> training it now (about 2 minutes) ...")
        from .microlm.train import main as train
        train()
    db = SessionLocal()
    try:
        with LOCK:
            eng.bootstrap(db)
    finally:
        db.close()
    task = asyncio.create_task(_supervisor()) if SUPERVISOR_ENABLED else None
    from .live import live_loop
    live_task = asyncio.create_task(live_loop(LOCK))
    yield
    live_task.cancel()
    if task:
        task.cancel()


app = FastAPI(title="SpaceSupply-Agent API", version="1.0.0", lifespan=lifespan,
              description="Autonomous multi-agent framework for (simulated) launch-vehicle assembly scheduling and component tracking.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ------------------------------------------------------------------ models
class ChatIn(BaseModel):
    message: str


class SimIn(BaseModel):
    type: str
    component_id: str | None = None
    workstation_id: str | None = None
    hours: int = 24


class LiveIn(BaseModel):
    running: bool | None = None
    speed: int | None = None
    chaos: bool | None = None


class ReplanIn(BaseModel):
    algorithm: str = "CPSAT"


# ------------------------------------------------------------------ basic
@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    return {"status": "ok", "now": iso(db, now_hour(db)), "microlm": MICROLM_PATH.exists(), "supervisor": SUPERVISOR_ENABLED}


@app.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db)):
    return eng.dashboard(db)


@app.get("/api/stages")
def stages(db: Session = Depends(get_db)):
    return eng.tracking.stage_progress(db)


# ------------------------------------------------------------------ components / inventory
def _comp(db, c: m.Component) -> dict:
    now = now_hour(db)
    return {"id": c.id, "name": c.name, "category": c.category, "stage_id": c.stage_id, "status": c.status, "group": GROUP_OF[c.status],
            "location": c.location, "quantity": c.quantity, "required": c.required_quantity, "inspection_status": c.inspection_status,
            "criticality": c.criticality, "supplier": c.supplier.name, "delay_hours": c.delay_hours,
            "ready_in_hours": 0 if c.status in m.USABLE else max(0, c.expected_ready_hour - now)}


@app.get("/api/components")
def components(status: str | None = None, stage: int | None = None, q: str | None = None, db: Session = Depends(get_db)):
    query = db.query(m.Component)
    if status:
        query = query.filter(m.Component.status == status.upper())
    if stage:
        query = query.filter(m.Component.stage_id == stage)
    rows = [_comp(db, c) for c in query.order_by(m.Component.id).all()]
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in r["id"].lower() or ql in r["name"].lower() or ql in r["location"].lower()]
    return rows


@app.get("/api/components/{cid}")
def component(cid: str, db: Session = Depends(get_db)):
    c = eng.tracking.find_component(db, cid)
    if not c:
        raise HTTPException(404, "Unknown component")
    users = [{"task_id": t.id, "name": t.name, "status": t.status} for t in eng.supply.tasks_needing(db, c.id, pending_only=False)]
    return {**_comp(db, c), "history": [{"hour": e.hour, "time": fmt(db, e.hour), "event": e.event_type, "from": e.from_status, "to": e.to_status,
                                         "location": e.location, "note": "" if e.note == "Seed history" else e.note} for e in eng.tracking.history(db, c.id)],
            "used_by": users, "delivery": eng.tracking.locate(db, c.id)["delivery"]}


@app.get("/api/inventory")
def inventory(db: Session = Depends(get_db)):
    return {"summary": eng.supply.summary(db), "rows": eng.supply.inventory_rows(db)}


@app.get("/api/deliveries")
def deliveries(db: Session = Depends(get_db)):
    now = now_hour(db)
    return [{"id": d.id, "component_id": d.component_id, "component": d.component.name, "supplier": d.supplier.name, "quantity": d.quantity,
             "eta": fmt(db, d.eta_hour), "eta_hours": d.eta_hour - now, "status": d.status, "delay_hours": d.delay_hours, "replacement": d.is_replacement}
            for d in db.query(m.Delivery).filter(m.Delivery.status.in_(["ON_TIME", "DELAYED", "ARRIVED"])).order_by(m.Delivery.eta_hour).all()]


# ------------------------------------------------------------------ schedule
@app.get("/api/schedule")
def schedule(db: Session = Depends(get_db)):
    ver = eng.scheduling.current_version(db)
    rows = eng.scheduling.schedule_rows(db)
    for r in rows:
        r["start_iso"], r["end_iso"] = iso(db, r["start_hour"]), iso(db, r["end_hour"])
        r["deadline_iso"] = iso(db, r["deadline_hour"])
    now = now_hour(db)
    ws = []
    for w in db.query(m.Workstation).order_by(m.Workstation.id).all():
        cur = next((r for r in rows if r["workstation"] == w.id and r["status"] == m.T_IN_PROGRESS), None)
        ws.append({"id": w.id, "name": w.name, "type": w.ws_type, "status": w.status, "free_in_hours": max(0, w.available_from - now),
                   "current_task": cur["id"] if cur else None, "maintenance_in_hours": (w.maintenance_due_hour - now) if w.maintenance_due_hour is not None else None})
    lo = min(r["start_hour"] for r in rows if r["start_hour"] is not None)
    hi = max(r["end_hour"] for r in rows if r["end_hour"] is not None)
    return {"now_hour": now, "now": iso(db, now), "start_iso": db.get(m.SimState, 1).start_iso, "min_hour": lo, "max_hour": hi,
            "version": {"id": ver.id, "algorithm": ver.algorithm, "trigger": ver.trigger, "created_hour": ver.created_hour, "metrics": json.loads(ver.metrics_json)},
            "tasks": rows, "workstations": ws}


@app.get("/api/schedule/versions")
def versions(db: Session = Depends(get_db)):
    return [{"id": v.id, "algorithm": v.algorithm, "trigger": v.trigger, "time": fmt(db, v.created_hour), "current": v.is_current,
             "metrics": json.loads(v.metrics_json)} for v in db.query(m.ScheduleVersion).order_by(m.ScheduleVersion.id.desc()).limit(20).all()]


@app.post("/api/schedule/replan")
def replan(body: ReplanIn, db: Session = Depends(get_db)):
    with LOCK:
        try:
            res = eng.scheduling.plan(db, body.algorithm, trigger=f"Manual re-plan ({body.algorithm})")
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        eng.monitoring.scan(db)
        db.commit()
    return res


@app.get("/api/schedule/compare")
def compare(db: Session = Depends(get_db)):
    with LOCK:
        live = eng.scheduling.compare(db)
    bench = json.loads(BENCHMARK_PATH.read_text()) if BENCHMARK_PATH.exists() else None
    return {"live": live, "benchmark": bench, "objective": "10 x priority-weighted tardiness + makespan (lower is better)"}


@app.get("/api/tasks/{tid}")
def task(tid: str, db: Session = Depends(get_db)):
    t = db.get(m.Task, tid.upper())
    if not t:
        raise HTTPException(404, "Unknown task")
    reqs = [{"component_id": r.component_id, "name": db.get(m.Component, r.component_id).name, "quantity": r.quantity}
            for r in db.query(m.TaskRequirement).filter(m.TaskRequirement.task_id == t.id)]
    return {"readiness": eng.scheduling.task_readiness(db, t.id), "explanation": eng.scheduling.explain_task(db, t.id), "requirements": reqs}


# ------------------------------------------------------------------ alerts / agents
@app.get("/api/alerts")
def alerts(status: str | None = None, db: Session = Depends(get_db)):
    q = db.query(m.Alert)
    if status:
        q = q.filter(m.Alert.status == status.upper())
    rank = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
    rows = q.order_by(m.Alert.id.desc()).limit(200).all()
    rows.sort(key=lambda a: (a.status == "RESOLVED", rank[a.severity], -a.id))
    return [eng.alert_dict(db, a) for a in rows]


@app.post("/api/alerts/{aid}/ack")
def ack(aid: int, db: Session = Depends(get_db)):
    with LOCK:
        a = db.get(m.Alert, aid)
        if not a:
            raise HTTPException(404, "Unknown alert")
        a.status = "ACKNOWLEDGED"
        db.commit()
    return eng.alert_dict(db, a)


@app.get("/api/agents")
def agents(db: Session = Depends(get_db)):
    logs = db.query(m.AgentLog).order_by(m.AgentLog.id.desc()).limit(40).all()
    return {"agents": eng.agent_status(db), "log": [{"agent": l.agent, "message": l.message, "time": fmt(db, l.hour)} for l in logs]}


# ------------------------------------------------------------------ chat / micro LM
@app.post("/api/chat")
def chat_endpoint(body: ChatIn, db: Session = Depends(get_db)):
    from .orchestrator import chat
    if not body.message.strip():
        raise HTTPException(400, "Empty message")
    with LOCK:
        return chat(db, body.message.strip()[:400])


@app.get("/api/chat/suggest")
def suggest(q: str = Query("", max_length=200)):
    from .microlm.infer import get_nlu
    return {"suggestions": get_nlu().suggest(q) if q.strip() else []}


@app.get("/api/model")
def model_info():
    from . import llm
    data = json.loads(MICROLM_METRICS.read_text()) if MICROLM_METRICS.exists() else {}
    data["qwen_layer"] = {"enabled": llm.available(), "model": llm.QWEN_MODEL}
    return data


# ------------------------------------------------------------------ live mode
@app.get("/api/live")
def live_state(since: int = 0):
    from .live import live
    return live.state(since)


@app.post("/api/live")
def live_config(body: LiveIn):
    from .live import live
    try:
        return live.configure(body.running, body.speed, body.chaos)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


# ------------------------------------------------------------------ simulation
@app.post("/api/simulate")
def simulate(body: SimIn, db: Session = Depends(get_db)):
    with LOCK:
        try:
            res = eng.handle_event(db, body.model_dump())
            from .live import live
            live.push(db, "DISRUPTION" if body.type.upper() != "ADVANCE_TIME" else "SYSTEM",
                      f"Manual: {res.get('trigger') or body.type}", "WARNING")
            return res
        except (ValueError, KeyError) as exc:
            db.rollback()
            raise HTTPException(400, f"{type(exc).__name__}: {exc}")


@app.post("/api/reset")
def reset(db: Session = Depends(get_db)):
    with LOCK:
        from .live import live
        live.running = False
        live.clear()
        eng.reset(db)
        live.push(db, "SYSTEM", "Simulation reset to the initial plant state.", "INFO")
    return {"status": "reset"}


# ------------------------------------------------------------------ static frontend (production build)
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = DIST / path
        return FileResponse(f if f.is_file() else DIST / "index.html")

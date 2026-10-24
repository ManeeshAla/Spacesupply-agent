"""Launch-vehicle assembly dataset: suppliers, component lots, workstations and tasks."""
from __future__ import annotations

import json
import math
import random
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from . import models as m
from .lifecycle import EVENT_NAME, INSPECTION_HOURS, LOCATION, STATUS_ORDER

STAGES = [
    (1, "Stage 1 – Solid Booster", "Stage 1"),
    (2, "Stage 2 – Liquid Core Stage", "Stage 2"),
    (3, "Stage 3 – Upper Motor Stage", "Stage 3"),
    (4, "Stage 4 – Avionics Bay & Vehicle Integration", "Stage 4"),
]

WORKSTATIONS = [
    ("WS-01", "Inspection Lab", "INSPECTION"),
    ("WS-02", "Structure Bay 1", "STRUCTURE"),
    ("WS-03", "Structure Bay 2", "STRUCTURE"),
    ("WS-04", "Propulsion Bay", "PROPULSION"),
    ("WS-05", "Avionics Lab", "AVIONICS"),
    ("WS-06", "Integration Hall", "INTEGRATION"),
    ("WS-07", "Static Test Cell", "TEST"),
]

# suppliers: (id, name, reliability, lead_time_days)
SUPPLIERS = [
    ("SUP-01", "Orbital Forge Industries", 0.93, 6),
    ("SUP-02", "Aerotek Precision Works", 0.90, 8),
    ("SUP-03", "NovaFlow Hydraulics", 0.86, 7),
    ("SUP-04", "Helios Avionics Pvt Ltd", 0.91, 10),
    ("SUP-05", "Stellar Alloys & Casings", 0.88, 9),
    ("SUP-06", "Cryon Valve Systems", 0.84, 7),
    ("SUP-07", "Pragati Electronics", 0.92, 5),
    ("SUP-08", "Sagar Composites", 0.89, 8),
]
SUPPLIER_BY_CAT = {
    "STRUCTURE": ["SUP-05", "SUP-08"], "PROPULSION": ["SUP-01", "SUP-06"],
    "HYDRAULIC": ["SUP-03"], "AVIONICS": ["SUP-04", "SUP-07"], "ELECTRICAL": ["SUP-07"],
    "SEALING": ["SUP-02"], "INSTRUMENTATION": ["SUP-04", "SUP-07"], "MECHANISM": ["SUP-02", "SUP-06"],
}

# (name, category, qty, criticality, explicit id)
def C(name, cat, qty=1, crit="NORMAL", cid=None):
    return (name, cat, qty, crit, cid)

# (num, name, stage, ws_type, duration_h, priority, [dep nums], [components])
TASKS = [
    # ---------------- Stage 1 : Solid booster ----------------
    (1, "Booster Casing Inspection", 1, "INSPECTION", 6, 3, [], [C("Booster Casing Segment", "STRUCTURE", 4, "HIGH"), C("Casing Sealing Ring", "SEALING", 8)]),
    (2, "Booster Casing Assembly", 1, "STRUCTURE", 12, 4, [1], [C("Casing Joint Clamp", "STRUCTURE", 12), C("Thermal Liner Panel", "STRUCTURE", 6)]),
    (3, "Booster Nozzle Assembly", 1, "PROPULSION", 10, 4, [1], [C("Nozzle Throat Insert", "PROPULSION", 1, "HIGH"), C("Nozzle Flex Seal", "SEALING", 2)]),
    (4, "Booster Igniter Installation", 1, "PROPULSION", 6, 5, [2], [C("Igniter Assembly", "PROPULSION", 1, "CRITICAL"), C("Safe-Arm Device", "MECHANISM", 1, "CRITICAL")]),
    (5, "Thrust Vector Actuator Fit", 1, "PROPULSION", 8, 4, [3], [C("Electro-Mechanical Actuator", "MECHANISM", 2, "HIGH"), C("Actuator Mount Bracket", "STRUCTURE", 4)]),
    (6, "Booster Avionics Harness", 1, "AVIONICS", 6, 3, [2], [C("Booster Wiring Harness", "ELECTRICAL", 1), C("Pyro Firing Unit", "AVIONICS", 2, "HIGH")]),
    (7, "Booster Leak & Pressure Test", 1, "TEST", 8, 5, [4, 5], [C("Test Pressure Gauge", "INSTRUMENTATION", 3), C("Test Blanking Plug", "MECHANISM", 4)]),
    (8, "Stage 1 Acceptance Review", 1, "INSPECTION", 4, 5, [6, 7], [C("Acceptance Seal Kit", "SEALING", 1)]),
    # ---------------- Stage 2 : Liquid core ----------------
    (9, "Core Component Inspection", 2, "INSPECTION", 8, 4, [], [C("Core Tank Barrel Section", "STRUCTURE", 3, "HIGH"), C("Tank Dome Cap", "STRUCTURE", 2)]),
    (10, "Stage 2 Tank Fabrication", 2, "STRUCTURE", 16, 4, [9], [C("Propellant Tank Skin Panel", "STRUCTURE", 8), C("Anti-Slosh Baffle", "STRUCTURE", 4), C("Tank Weld Filler Kit", "STRUCTURE", 2)]),
    (11, "Stage 2 Tank Integration", 2, "STRUCTURE", 10, 4, [10], [C("Tank Interstage Ring", "STRUCTURE", 2), C("Tank Pressurisation Line", "PROPULSION", 2), C("Level Sensor Probe", "INSTRUMENTATION", 4)]),
    (12, "Engine Mount Assembly", 2, "PROPULSION", 12, 5, [9], [C("Engine Thrust Frame", "STRUCTURE", 1, "HIGH"), C("Gimbal Bearing", "MECHANISM", 2, "HIGH"), C("Mount Fastener Set", "STRUCTURE", 24)]),
    (13, "Turbopump & Engine Installation", 2, "PROPULSION", 14, 5, [12], [C("Fuel Pump", "PROPULSION", 1, "CRITICAL", 21), C("Oxidiser Pump", "PROPULSION", 1, "CRITICAL"), C("Main Engine Assembly", "PROPULSION", 1, "CRITICAL")]),
    (14, "Fuel Line Connection", 2, "STRUCTURE", 8, 4, [11, 13], [C("Cryogenic Feed Line", "PROPULSION", 3, "HIGH"), C("Main Propellant Valve", "PROPULSION", 2, "CRITICAL"), C("Flexible Bellows Joint", "SEALING", 4)]),
    (15, "Stage 2 Avionics System Check", 2, "AVIONICS", 8, 4, [11], [C("Stage 2 Flight Controller", "AVIONICS", 1, "CRITICAL"), C("Rate Gyro Package", "AVIONICS", 2, "HIGH"), C("Stage 2 Wiring Harness", "ELECTRICAL", 1)]),
    (16, "Stage 2 Hot-Fire Readiness Test", 2, "TEST", 12, 5, [14, 15], [C("Hydraulic Motor", "HYDRAULIC", 1, "HIGH", 56), C("Hot-Fire Instrumentation Kit", "INSTRUMENTATION", 1), C("Flame Deflector Liner", "STRUCTURE", 2)]),
    (17, "Stage 2 Acceptance Review", 2, "INSPECTION", 4, 5, [16], [C("Stage 2 Acceptance Seal Kit", "SEALING", 1)]),
    # ---------------- Stage 3 : Upper motor ----------------
    (18, "Upper Motor Casing Inspection", 3, "INSPECTION", 6, 3, [], [C("Upper Motor Casing Segment", "STRUCTURE", 3, "HIGH"), C("Upper Casing O-Ring", "SEALING", 6)]),
    (19, "Upper Motor Casing Assembly", 3, "STRUCTURE", 12, 3, [18], [C("Upper Casing Clamp", "STRUCTURE", 8), C("Upper Thermal Liner", "STRUCTURE", 4)]),
    (20, "Upper Motor Nozzle Assembly", 3, "PROPULSION", 8, 3, [18], [C("Upper Nozzle Insert", "PROPULSION", 1, "HIGH"), C("Upper Nozzle Seal", "SEALING", 2)]),
    (21, "Upper Motor Igniter & Safe-Arm Fit", 3, "PROPULSION", 6, 4, [19], [C("Upper Igniter", "PROPULSION", 1, "CRITICAL"), C("Upper Safe-Arm Unit", "MECHANISM", 1, "CRITICAL")]),
    (22, "Attitude Control Thruster Fit", 3, "PROPULSION", 8, 3, [20], [C("Attitude Thruster", "PROPULSION", 4, "HIGH"), C("Thruster Valve", "PROPULSION", 4), C("Cold-Gas Bottle", "PROPULSION", 2)]),
    (23, "Stage 3 Avionics Harness", 3, "AVIONICS", 6, 3, [19], [C("Stage 3 Wiring Harness", "ELECTRICAL", 1), C("Separation Pyro Unit", "AVIONICS", 2, "HIGH")]),
    (24, "Stage 3 Pressure Test", 3, "TEST", 8, 4, [21, 22], [C("Pressure Sensor", "INSTRUMENTATION", 4, "HIGH", 78), C("Test Manifold", "INSTRUMENTATION", 1)]),
    (25, "Stage 3 Acceptance Review", 3, "INSPECTION", 4, 4, [23, 24], [C("Stage 3 Acceptance Seal Kit", "SEALING", 1)]),
    # ---------------- Stage 4 : Avionics bay & integration ----------------
    (26, "Avionics Bay Component Inspection", 4, "INSPECTION", 6, 4, [], [C("Avionics Bay Shell", "STRUCTURE", 1, "HIGH"), C("Equipment Deck Plate", "STRUCTURE", 2)]),
    (27, "Avionics Bay Structure Assembly", 4, "STRUCTURE", 10, 3, [26], [C("Deck Mounting Rail", "STRUCTURE", 6), C("Vibration Isolator", "MECHANISM", 8)]),
    (28, "Flight Computer Installation", 4, "AVIONICS", 8, 5, [27], [C("Avionics Unit", "AVIONICS", 1, "CRITICAL", 34), C("Flight Computer Card", "AVIONICS", 2, "CRITICAL"), C("Power Conditioning Unit", "ELECTRICAL", 1, "HIGH")]),
    (29, "Inertial Navigation Calibration", 4, "AVIONICS", 10, 5, [28], [C("Inertial Measurement Unit", "AVIONICS", 1, "CRITICAL"), C("Calibration Fixture", "INSTRUMENTATION", 1)]),
    (30, "Telemetry & Tracking Fit", 4, "AVIONICS", 8, 4, [27], [C("Telemetry Transmitter", "AVIONICS", 2, "HIGH"), C("Tracking Transponder", "AVIONICS", 1, "HIGH"), C("Antenna Assembly", "AVIONICS", 3)]),
    (31, "Payload Fairing Assembly", 4, "STRUCTURE", 14, 3, [26], [C("Fairing Half-Shell", "STRUCTURE", 2, "HIGH"), C("Fairing Separation Mechanism", "MECHANISM", 1, "CRITICAL"), C("Acoustic Blanket", "STRUCTURE", 6)]),
    (32, "Stage 4 Systems Test", 4, "TEST", 10, 5, [29, 30], [C("Systems Test Harness", "ELECTRICAL", 1), C("Ground Test Computer", "INSTRUMENTATION", 1)]),
    (33, "Stage 4 Acceptance Review", 4, "INSPECTION", 4, 4, [31, 32], [C("Stage 4 Acceptance Seal Kit", "SEALING", 1)]),
    (34, "Stage 1–2 Stacking", 4, "INTEGRATION", 12, 5, [8, 17], [C("Interstage Coupling Ring", "STRUCTURE", 1, "CRITICAL"), C("Stacking Alignment Jig", "MECHANISM", 1), C("Separation Bolt Set", "MECHANISM", 12, "HIGH")]),
    (35, "Stage 3 Stacking", 4, "INTEGRATION", 10, 5, [34, 25], [C("Stage 2–3 Adapter", "STRUCTURE", 1, "CRITICAL"), C("Stacking Fastener Kit", "STRUCTURE", 20)]),
    (36, "Upper Section & Fairing Integration", 4, "INTEGRATION", 12, 5, [35, 33], [C("Stage 3–4 Adapter", "STRUCTURE", 1, "CRITICAL"), C("Umbilical Interface Panel", "ELECTRICAL", 2)]),
    (37, "Integrated Vehicle Electrical Check", 4, "AVIONICS", 10, 5, [36], [C("Vehicle Checkout Cable Set", "ELECTRICAL", 1), C("Range Safety Receiver", "AVIONICS", 2, "CRITICAL")]),
    (38, "Final Integrated Vehicle Test", 4, "TEST", 14, 5, [37], [C("Integrated Test Instrumentation", "INSTRUMENTATION", 1, "HIGH"), C("Launch Pad Interface Kit", "MECHANISM", 1)]),
    (39, "Launch Readiness Review", 4, "INSPECTION", 6, 5, [38], [C("Flight Readiness Documentation Pack", "INSTRUMENTATION", 1)]),
]

COMPLETED = set(range(1, 9)) | {9, 10, 12} | {18, 19, 20}
IN_PROGRESS = {11, 21}  # task 13 (needs the Fuel Pump, CMP-021) is intentionally waiting: see FORCED below


def _tid(n: int) -> str:
    return f"T-{n:03d}"


def _cid(n: int) -> str:
    return f"CMP-{n:03d}"


def _log_event(db: Session, comp: m.Component, hour: int, status_to: str, status_from: str | None, note: str = ""):
    db.add(m.ComponentEvent(
        component_id=comp.id, hour=hour, event_type=EVENT_NAME[status_to],
        from_status=status_from, to_status=status_to, location=LOCATION[status_to] if status_to != m.INSTALLED else comp.location,
        note=note))


def reset_schema():
    from .database import Base, engine
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def seed(db: Session, rng_seed: int = 42) -> None:
    """Populate the database with the starting scenario (idempotent only after reset_schema)."""
    rng = random.Random(rng_seed)
    start = datetime.now().replace(minute=0, second=0, microsecond=0)
    db.add(m.SimState(id=1, now_hour=0, start_iso=start.isoformat()))
    for sid, name, short in STAGES:
        db.add(m.Stage(id=sid, name=name, short_name=short))
    for wid, name, t in WORKSTATIONS:
        db.add(m.Workstation(id=wid, name=name, ws_type=t))
    for sid, name, rel, lead in SUPPLIERS:
        db.add(m.Supplier(id=sid, name=name, reliability=rel, lead_time_days=lead))
    db.flush()

    # ---------------- tasks (history for completed / in-progress) ----------------
    dur = {n: d for (n, _, _, _, d, _, _, _) in TASKS}
    deps = {n: ds for (n, _, _, _, _, _, ds, _) in TASKS}
    wstype = {n: t for (n, _, _, t, _, _, _, _) in TASKS}
    ws_by_type: dict[str, list[str]] = {}
    for wid, _, t in WORKSTATIONS:
        ws_by_type.setdefault(t, []).append(wid)

    # historic schedule for completed tasks (resource-aware list scheduling in the past)
    machine_free = {w[0]: 0 for w in WORKSTATIONS}
    hist: dict[int, tuple[str, int, int]] = {}
    for n in sorted(COMPLETED, key=lambda x: x):
        ready = max([hist[d][2] for d in deps[n] if d in hist], default=0)
        best = min(ws_by_type[wstype[n]], key=lambda w: max(ready, machine_free[w]))
        s = max(ready, machine_free[best])
        hist[n] = (best, s, s + dur[n])
        machine_free[best] = s + dur[n]
    shift = -8 - max(e for (_, _, e) in hist.values())
    hist = {n: (w, s + shift, e + shift) for n, (w, s, e) in hist.items()}

    used_ws_now: set[str] = set()
    prog: dict[int, tuple[str, int, int]] = {}
    for n in sorted(IN_PROGRESS):
        pred_end = max([hist[d][2] for d in deps[n] if d in hist], default=-10)
        s = min(-1, max(pred_end, -rng.randint(2, 5)))
        e = s + dur[n]
        w = next(x for x in ws_by_type[wstype[n]] if x not in used_ws_now)
        used_ws_now.add(w)
        prog[n] = (w, s, e)

    # CPM for deadlines (resource-free, with component release times filled in later -> use rough estimate)
    ef: dict[int, int] = {}
    for n in range(1, len(TASKS) + 1):
        if n in COMPLETED:
            ef[n] = 0
        elif n in IN_PROGRESS:
            ef[n] = prog[n][2]
        else:
            ef[n] = max([ef[d] for d in deps[n]], default=0) + dur[n]
    project_cp = max(ef.values())
    project_deadline = int(project_cp * 1.30) + 18
    succ: dict[int, list[int]] = {n: [] for n in dur}
    for n, ds in deps.items():
        for d in ds:
            succ[d].append(n)
    lf: dict[int, int] = {}
    for n in range(len(TASKS), 0, -1):
        lf[n] = min([lf[s] - dur[s] for s in succ[n]], default=project_deadline)

    for (n, name, stage, t, d, prio, ds, _comps) in TASKS:
        task = m.Task(id=_tid(n), name=name, stage_id=stage, ws_type=t, duration=d, priority=prio,
                      deadline_hour=0)
        if n in COMPLETED:
            task.status, task.workstation_id, task.start_hour, task.end_hour = m.T_COMPLETED, hist[n][0], hist[n][1], hist[n][2]
        elif n in IN_PROGRESS:
            task.status, task.workstation_id, task.start_hour, task.end_hour = m.T_IN_PROGRESS, prog[n][0], prog[n][1], prog[n][2]
        db.add(task)
    db.flush()
    for (n, *_rest) in TASKS:
        for d_ in deps[n]:
            db.add(m.TaskDependency(task_id=_tid(n), depends_on_id=_tid(d_)))
    for n, (w, s, e) in prog.items():
        ws = db.get(m.Workstation, w)
        ws.available_from = e
    db.get(m.Workstation, "WS-05").maintenance_due_hour = 52

    # ---------------- components ----------------
    explicit = {c[4]: n for (n, _, _, _, _, _, _, comps) in TASKS for c in comps if c[4]}
    next_free = iter(i for i in range(1, 1000) if i not in set(explicit))
    order: list[tuple[int, tuple]] = []
    for (n, _name, _stage, _t, _d, _p, _ds, comps) in TASKS:
        for c in comps:
            cid_num = c[4] if c[4] else next(next_free)
            order.append((cid_num, (n, c)))
    order.sort(key=lambda x: x[0])

    near_term_tasks = {n for n in range(1, len(TASKS) + 1) if n not in COMPLETED and n not in IN_PROGRESS
                       and all((d in COMPLETED or d in IN_PROGRESS) for d in deps[n])}

    FORCED = {  # component number -> (status, eta_hour or None)
        21: (m.ORDERED, 14),      # Fuel pump arriving in 14h (the demo scenario)
        34: (m.ORDERED, 60),      # Avionics unit
        56: (m.ORDERED, 40),      # Hydraulic motor
        78: (m.ORDERED, 70),      # Pressure sensor
    }

    FORCED_BY_NAME = {"Stage 4 Acceptance Seal Kit": (m.REJECTED, 40)}   # a rejected part with enough slack
    comp_rows: list[m.Component] = []
    delivery_n = 0
    for cid_num, (n, c) in order:
        name, cat, qty, crit, _ = c
        stage = next(t[2] for t in TASKS if t[0] == n)
        sup = rng.choice(SUPPLIER_BY_CAT[cat])
        comp = m.Component(id=_cid(cid_num), name=name, category=cat, stage_id=stage, supplier_id=sup,
                           quantity=qty, required_quantity=qty, criticality=crit)
        eta = None
        if n in COMPLETED:
            status = m.INSTALLED
        elif n in IN_PROGRESS:
            status = m.IN_ASSEMBLY_BAY
        elif cid_num in FORCED:
            status, eta = FORCED[cid_num]
        elif name in FORCED_BY_NAME:
            status, eta = FORCED_BY_NAME[name]
        else:
            r = rng.random()
            if n in near_term_tasks:
                cuts = [(0.52, m.IN_WAREHOUSE), (0.70, m.APPROVED), (0.82, m.IN_INSPECTION),
                        (0.90, m.INSPECTION_PENDING), (1.01, m.ORDERED)]
            else:
                cuts = [(0.40, m.IN_WAREHOUSE), (0.52, m.APPROVED), (0.60, m.IN_INSPECTION),
                        (0.66, m.INSPECTION_PENDING), (1.01, m.ORDERED)]
            status = next(s for cut, s in cuts if r < cut)
            if status == m.ORDERED:
                eta = rng.randint(12, 120)
            if status == m.REJECTED:
                eta = rng.randint(30, 80)
        comp.status = status
        comp.location = LOCATION[status] if status != m.INSTALLED else f"Installed – Stage {stage}"
        if status == m.IN_ASSEMBLY_BAY:
            comp.location = f"Assembly Bay – {prog[n][0]}"
        comp.inspection_status = {
            m.ORDERED: "PENDING", m.RECEIVED: "PENDING", m.INSPECTION_PENDING: "PENDING",
            m.IN_INSPECTION: "IN_PROGRESS", m.REJECTED: "FAILED"}.get(status, "PASSED")
        if n in COMPLETED:
            comp.required_quantity = 0
        # readiness time
        if status in m.USABLE:
            comp.expected_ready_hour = 0
        elif status == m.INSPECTION_PENDING:
            comp.expected_ready_hour = rng.randint(8, 16)
        elif status == m.IN_INSPECTION:
            comp.expected_ready_hour = rng.randint(3, 8)
        elif status in (m.ORDERED, m.REJECTED):
            comp.expected_ready_hour = (eta or 24) + INSPECTION_HOURS
        db.add(comp)
        comp_rows.append(comp)
        db.flush()
        db.add(m.TaskRequirement(task_id=_tid(n), component_id=comp.id, quantity=qty))

        # on-hand quantity: on order / quarantined -> 0 on hand
        if status in (m.ORDERED, m.REJECTED):
            comp.quantity = 0
            delivery_n += 1
            delay = 0
            dstatus = "ON_TIME"
            db.add(m.Delivery(id=f"DEL-{delivery_n:03d}", component_id=comp.id, supplier_id=sup, quantity=qty,
                              eta_hour=eta or 24, status=dstatus, delay_hours=delay, is_replacement=(status == m.REJECTED)))

        # event history (backwards in time from the hour the current status was reached)
        if status == m.REJECTED:
            path = [m.ORDERED, m.RECEIVED, m.INSPECTION_PENDING, m.IN_INSPECTION, m.REJECTED]
        else:
            path = STATUS_ORDER[: STATUS_ORDER.index(status) + 1]
        if n in COMPLETED:
            anchor = hist[n][1]
        elif n in IN_PROGRESS:
            anchor = prog[n][1]
        else:
            anchor = -rng.randint(1, 6)
        t_hour = anchor
        stamps = []
        for i in range(len(path) - 1, -1, -1):
            stamps.append(t_hour)
            t_hour -= rng.randint(3, 20) if path[i] != m.ORDERED else rng.randint(40, 120)
        stamps.reverse()
        prev = None
        for st, hr in zip(path, stamps):
            if status == m.ORDERED and st == m.ORDERED:
                hr = -rng.randint(10, 60)
            _log_event(db, comp, hr, st, prev, "Seed history")
            prev = st
        if status == m.REJECTED:
            db.add(m.ComponentEvent(component_id=comp.id, hour=-1, event_type="REPLACEMENT_ORDERED",
                                    from_status=m.REJECTED, to_status=m.REJECTED, location=LOCATION[m.REJECTED],
                                    note="Failed inspection; replacement requested from supplier"))

    db.flush()

    # a partial shipment: Pressure Sensor-like shortage example (14 of 20 on hand, 6 incoming)
    pending_fastener = next((c for c in comp_rows if c.name == "Stacking Fastener Kit"), None)
    if pending_fastener is not None:
        pending_fastener.status = m.IN_WAREHOUSE
        pending_fastener.location = LOCATION[m.IN_WAREHOUSE]
        pending_fastener.inspection_status = "PASSED"
        pending_fastener.quantity = 14
        pending_fastener.required_quantity = 20
        pending_fastener.expected_ready_hour = 30 + INSPECTION_HOURS
        delivery_n += 1
        db.add(m.Delivery(id=f"DEL-{delivery_n:03d}", component_id=pending_fastener.id, supplier_id=pending_fastener.supplier_id,
                          quantity=6, eta_hour=30, status="ON_TIME"))

    db.flush()
    _assign_deadlines(db, rng, deps, dur)
    db.commit()


def _assign_deadlines(db: Session, rng: random.Random, deps, dur) -> None:
    """Component-aware critical-path deadlines: tight enough that resource conflicts matter."""
    comps = {c.id: c for c in db.query(m.Component).all()}
    reqs: dict[str, list] = {}
    for r in db.query(m.TaskRequirement).all():
        reqs.setdefault(r.task_id, []).append(r)
    tasks = {t.id: t for t in db.query(m.Task).all()}
    ef: dict[int, int] = {}
    for n in range(1, len(TASKS) + 1):
        t = tasks[_tid(n)]
        if t.status == m.T_COMPLETED:
            ef[n] = 0
        elif t.status == m.T_IN_PROGRESS:
            ef[n] = t.end_hour
        else:
            rel = 0
            for r in reqs.get(t.id, []):
                c = comps[r.component_id]
                if not (c.status in m.USABLE and c.quantity >= r.quantity):
                    rel = max(rel, c.expected_ready_hour)
            ef[n] = max([rel] + [ef[d] for d in deps[n]]) + dur[n]
    cp = max(ef.values())
    project_deadline = int(cp * 1.12) + 8
    succ: dict[int, list[int]] = {n: [] for n in dur}
    for n, ds in deps.items():
        for d in ds:
            succ[d].append(n)
    # stage milestones (contractual acceptance-review dates) are tighter than the final date,
    # so tasks of different stages compete for the same workstations
    caps = {8: None, 17: None, 25: None, 33: None}
    for acc in caps:
        caps[acc] = int(ef[acc] * 1.10) + 6
    lf: dict[int, int] = {}
    for n in range(len(TASKS), 0, -1):
        lf[n] = min([lf[x] - dur[x] for x in succ[n]], default=project_deadline)
        if n in caps and tasks[_tid(n)].status == m.T_PENDING:
            lf[n] = min(lf[n], caps[n])
    for n in range(1, len(TASKS) + 1):
        tasks[_tid(n)].deadline_hour = lf[n] + rng.randint(0, 3)


def ensure_seeded(db: Session) -> None:
    from .database import Base, engine
    Base.metadata.create_all(engine)
    if db.get(m.SimState, 1) is None:
        seed(db)
